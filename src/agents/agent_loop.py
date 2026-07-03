"""Shared agent loop — fetch prompt → recall memory → LLM → tool calls → final.

Used by DMResponder and InGroupResponder. The LLM is asked up to ``max_iters``
times; each iteration that comes back with ``tool_calls`` is dispatched via
``ToolDispatcher`` and the results are appended as ``role='tool'`` messages.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.context import current as current_trace
from src.domain.memory import MemoryScope
from src.llm.base import ChatMessage, LLMRequest, ToolSpec
from src.repositories.action_items import ActionItemsRepo
from src.repositories.base import BossContext
from src.repositories.prompts import PromptsRepo
from src.repositories.reminders import RemindersRepo
from src.tools import registry
from src.tools.base import ToolContext
from src.tools.dispatcher import ToolDispatcher
from src.tools.registry import _REGISTRY as _TOOL_REGISTRY

import structlog

log = logging.getLogger(__name__)
_slog = structlog.get_logger()


_FALLBACK_REPLY = "Em xin lỗi, hệ thống đang gặp trục trặc — sếp thử lại sau ít phút."
_LOOP_REPLY = "(em xin lỗi, em hơi loạn — vui lòng thử lại)"

# Responder là thư ký bám sát dữ kiện — temp thấp để bớt trôi/bịa và trả lời nhất
# quán (extract dùng 0.2, reconcile 0.1). Mặc định LLMRequest là 0.7 (quá cao cho QA).
_RESPONDER_TEMPERATURE = 0.3


async def _load_prompt(prompt_key: str, ctx) -> str:
    if not prompt_key:
        return ""
    repo = PromptsRepo(ctx.db, BossContext(ctx.boss.id, "boss"))
    p = await repo.get_active(prompt_key)
    return (p.body if p else "") or ""


def _bot_language_directive(language: str | None) -> str | None:
    """Chỉ thị ngôn ngữ trả lời của bot theo cài đặt của boss.
    'auto' / None → không ép (bot trả lời theo ngôn ngữ người nhắn)."""
    return {
        "vi": "Luôn trả lời bằng tiếng Việt, bất kể người dùng nhắn bằng ngôn ngữ nào.",
        "en": "Always respond in English, regardless of the language the user writes in.",
    }.get((language or "").lower())


def _current_time_directive(tz: str | None) -> str:
    """Mốc thời gian hiện tại theo tz của boss — để agent suy luận 'hôm nay',
    'ngày mai', 'cuối tuần', '2 tiếng nữa'… mà không phải gọi tool, và không bao
    giờ nói 'tôi không biết ngày giờ'."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = tz or "Asia/Ho_Chi_Minh"
    try:
        now = datetime.now(ZoneInfo(zone))
    except Exception:
        zone = "Asia/Ho_Chi_Minh"
        now = datetime.now(ZoneInfo(zone))
    weekday = [
        "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"
    ][now.weekday()]
    return (
        f"Bối cảnh thời gian hiện tại: {weekday}, {now:%d/%m/%Y %H:%M} "
        f"(múi giờ {zone}). Dùng đúng mốc này cho mọi suy luận thời gian "
        "(hôm nay, ngày mai, cuối tuần, '2 tiếng nữa'…). "
        "Khi xếp hạng/đánh giá deadline: mốc đã QUA so với hiện tại là việc 'trễ hạn' "
        "(nêu riêng), KHÔNG được tính là 'sắp tới'; 'sắp tới hạn' CHỈ gồm các mốc còn ở "
        "tương lai, gần nhất = mốc tương lai sớm nhất. Tuyệt đối KHÔNG nói rằng bạn "
        "không biết ngày giờ hiện tại."
    )


def _format_memory(semantic, episodic, reminders, action_items) -> str:
    lines: list[str] = []
    if semantic:
        lines.append("== Semantic ==")
        for m in semantic:
            tag = f"{m.key}: " if m.key else ""
            lines.append(f"- {tag}{m.content}")
    if episodic:
        lines.append("== Episodic ==")
        for m in episodic:
            lines.append(f"- {m.content}")
    if reminders or action_items:
        lines.append("== Prospective ==")
        if reminders:
            lines.append("Reminders (pending):")
            for r in reminders:
                due = r.due_at.isoformat() if r.due_at else "?"
                where = f" @{r.chat_id}" if r.chat_id else ""
                lines.append(f"- #{r.id} [{due}{where}] {r.text}")
        if action_items:
            lines.append("Action items (open):")
            for a in action_items:
                who = f"{a.assignee_name}: " if a.assignee_name else ""
                due = f" (due {a.due_at.isoformat()})" if a.due_at else ""
                lines.append(f"- #{a.id} {who}{a.text}{due}")
    return "\n".join(lines) if lines else "(no memory)"


def _to_toolspec(td) -> ToolSpec:
    return ToolSpec(name=td.name, description=td.description, parameters=td.parameters)


async def _allowed_tools(cfg, ctx) -> set[str]:
    """Compose the per-op tool allowlist with enabled plugin tools.

    Convention: plugin tools are namespaced ``<plugin_id>_<tool_name>``
    (e.g. ``gcal_create_event``). If ``boss_integrations.enabled`` for the
    plugin is true, *all* of that plugin's registered tools are added to
    the allowlist for this boss.
    """
    # Core/built-in tools (cfg.tools, từ _REGISTRY): LUÔN bật cho MỌI boss —
    # không tắt được, không tính vào cap. Đây là bộ lõi để bot vận hành
    # (search_knowledge, read/refresh note, set/list reminder, action items,
    # find_exact_quote, remember, current_time…). Cap chỉ áp cho integration.
    # (Trước đây intersect với boss_active_tools + cap max_active_tools khiến
    # boss trial chỉ có 5 tool ngẫu nhiên theo thứ tự registry → mất cả
    # search_knowledge, không dùng được tính năng lõi.)
    base: set[str] = set(cfg.tools or set())
    db = getattr(ctx, "db", None)
    boss = getattr(ctx, "boss", None)
    if db is None or boss is None:
        return base

    # Plugin/integration tools cộng thêm theo boss_integrations (bật/tắt + cap
    # riêng — mcp_slots), namespaced ``<plugin_id>_<tool_name>``.
    try:
        async with db.acquire() as c:
            rows = await c.fetch(
                """
                SELECT plugin_id FROM boss_integrations
                WHERE boss_id=$1 AND enabled=TRUE
                """,
                boss.id,
            )
    except Exception:
        log.exception("boss_integrations query failed")
        rows = []
    enabled = {r["plugin_id"] for r in rows}
    if enabled:
        for tname in _TOOL_REGISTRY:
            prefix = tname.split("_", 1)[0]
            if prefix in enabled:
                base.add(tname)

    return base


def _build_tool_ctx(ctx, op_name: str, event: dict | None = None) -> ToolContext:
    trace = current_trace()
    event = event or {}
    return ToolContext(
        boss_id=ctx.boss.id,
        boss_role="boss",
        pool=ctx.db,
        qdrant=getattr(ctx, "qdrant", None),
        bus=ctx.bus,
        memory=ctx.memory,
        retriever_factory=getattr(ctx, "retriever_factory", None),
        llm=ctx.llm,
        trace_id=(trace.trace_id if trace else "no-trace"),
        span_id=(trace.span_id if trace else "no-span"),
        chat_id=event.get("chat_id"),
        provider=event.get("provider"),
        chat_type=event.get("chat_type"),
        sender_provider_id=event.get("sender_provider_id"),
        sender_name=event.get("sender_name"),
    )



_HISTORY_SNIPPET = 400  # cắt mỗi tin — đủ ngữ cảnh, không phình token
_QUICK_ACKS = {"Để em xem...", "Em xem rồi trả lời ngay ạ."}


async def _history_limit(ctx, chat_type: str | None) -> int:
    """Số tin lịch sử: boss override (Settings) → mặc định superadmin
    (platform_settings) → 12. DM và nhóm là 2 knob riêng (user chốt 03/7)."""
    from src.services.platform_settings import get_setting

    col = "history_window_dm" if chat_type == "dm" else "history_window_group"
    override = None
    try:
        async with ctx.db.acquire() as c:
            override = await c.fetchval(
                f"SELECT {col} FROM users WHERE id=$1", ctx.boss.id)
    except Exception:
        log.exception("history override lookup failed")
    if override is not None:
        return max(0, min(50, int(override)))
    default = await get_setting(ctx.db, col, 12)
    try:
        return max(0, min(50, int(default)))
    except (TypeError, ValueError):
        return 12


async def _recent_history(ctx, event: dict) -> str:
    """Cửa sổ hội thoại gần đây của CHÍNH chat này (inbound + trả lời của bot).

    Thiếu nó thì mỗi lượt chat là một hòn đảo — bot quên ngay điều vừa nói
    trong cùng đoạn DM/nhóm (memory episodic là recall theo độ tương đồng,
    không thay được continuity theo lượt)."""
    chat_id, provider = event.get("chat_id"), event.get("provider")
    if not chat_id or not provider:
        return ""
    limit = await _history_limit(ctx, event.get("chat_type"))
    if limit <= 0:
        return ""  # 0 = tắt cửa sổ hội thoại
    try:
        async with ctx.db.acquire() as c:
            rows = await c.fetch(
                """
                (SELECT COALESCE(sender_name, 'Thành viên') AS who, text, ts
                   FROM messages
                  WHERE boss_id=$1 AND provider=$2 AND chat_id=$3 AND id <> $4
                    AND text IS NOT NULL)
                UNION ALL
                (SELECT 'Thư ký (em)' AS who, content AS text, sent_at AS ts
                   FROM outbound_messages
                  WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
                    AND status='sent')
                ORDER BY ts DESC LIMIT $5
                """,
                ctx.boss.id, provider, chat_id,
                event.get("message_id") or 0, limit,
            )
    except Exception:
        log.exception("recent history fetch failed")
        return ""
    lines = []
    for r in reversed(rows):  # cũ → mới
        text = (r["text"] or "").strip()
        if not text or text in _QUICK_ACKS:
            continue
        if len(text) > _HISTORY_SNIPPET:
            text = text[:_HISTORY_SNIPPET] + "…"
        lines.append(f"[{r['who']}]: {text}")
    if not lines:
        return ""
    return (
        "HỘI THOẠI GẦN ĐÂY trong chính đoạn chat này (cũ → mới, để nối mạch "
        "các lượt trước; tin cuối cùng bên dưới là tin đang trả lời):\n"
        + "\n".join(lines)
    )


async def run_agent(op_cls, event: dict, ctx, max_iters: int = 5) -> str:
    cfg = op_cls._op_config
    op_name = cfg.name

    # 1. System prompt (+ chỉ thị ngôn ngữ trả lời theo cài đặt của boss)
    system_prompt = await _load_prompt(cfg.prompt_key, ctx)
    lang_directive = _bot_language_directive(getattr(ctx.boss, "language", None))
    if lang_directive:
        system_prompt = f"{system_prompt}\n\n{lang_directive}"
    # Luôn cấp mốc thời gian hiện tại (theo tz boss) — bot vốn không biết "now".
    system_prompt = (
        f"{system_prompt}\n\n{_current_time_directive(getattr(ctx.boss, 'tz', None))}"
    )

    # 2. Memory recall (semantic + episodic + prospective when configured)
    semantic: list[Any] = []
    episodic: list[Any] = []
    reminders: list[Any] = []
    action_items: list[Any] = []
    boss_ctx = BossContext(ctx.boss.id, "boss")
    if "semantic" in (cfg.memory_scopes or []):
        try:
            semantic = await ctx.memory.recall(
                MemoryScope.SEMANTIC, None, ctx.boss.id, k=20
            )
        except Exception:
            log.exception("semantic memory recall failed")
    if "episodic" in (cfg.memory_scopes or []):
        try:
            episodic = await ctx.memory.recall(
                MemoryScope.EPISODIC, event.get("text", ""), ctx.boss.id, k=5
            )
        except Exception:
            log.exception("episodic memory recall failed")
    if "prospective" in (cfg.memory_scopes or []):
        try:
            reminders = (
                await RemindersRepo(ctx.db, boss_ctx).list_all(status="pending")
            )[:10]
        except Exception:
            log.exception("prospective reminders recall failed")
        try:
            action_items = (
                await ActionItemsRepo(ctx.db, boss_ctx).list_open()
            )[:10]
        except Exception:
            log.exception("prospective action_items recall failed")

    history_block = await _recent_history(ctx, event)
    msgs: list[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content="Memory:\n"
            + _format_memory(semantic, episodic, reminders, action_items),
            name="memory_block",
        ),
    ]
    if history_block:
        msgs.append(ChatMessage(role="user", content=history_block, name="history_block"))
    msgs.append(ChatMessage(role="user", content=event.get("text", "")))

    # 3. Tool surface (base allowlist + enabled plugin tools for this boss)
    allowed = await _allowed_tools(cfg, ctx)
    tools = [_to_toolspec(t) for t in registry.filter_for_op(op_name, allowed=allowed)]
    dispatcher = ToolDispatcher(ctx.db)
    tool_ctx = _build_tool_ctx(ctx, op_name=op_name, event=event)

    # 4. Loop
    for _ in range(max_iters):
        req = LLMRequest(
            feature=cfg.feature,
            messages=msgs,
            boss_id=ctx.boss.id,
            tools=tools or None,
            cache_prefix_hint=cfg.cache_prefix_hint or "after_semantic_memory",
            routing_hints={"op": op_name},
            temperature=_RESPONDER_TEMPERATURE,
        )
        try:
            resp = await ctx.llm.complete(req)
        except Exception:
            log.exception("llm.complete raised in agent_loop")
            return _FALLBACK_REPLY

        _slog.info(
            "agent_llm_turn", op=op_name, finish=resp.finish_reason,
            content_len=len(resp.content or ""), n_tools=len(resp.tool_calls),
            content_tail=(resp.content or "")[-120:],
        )
        if resp.status != "ok":
            log.warning("llm response non-ok status=%s err=%s", resp.status, resp.error)
            return resp.content or _FALLBACK_REPLY

        if not resp.tool_calls:
            return resp.content or ""

        # Append assistant turn KÈM tool_calls — thiếu là OpenAI 400
        # ("messages with role 'tool' must be a response to ... 'tool_calls'").
        msgs.append(
            ChatMessage(
                role="assistant",
                content=resp.content or "",
                tool_calls=resp.tool_calls,
            )
        )
        for tc in resp.tool_calls:
            _slog.info("agent_tool_call", op=op_name, name=tc.name, args=tc.arguments)
        results = await dispatcher.call_batch(resp.tool_calls, tool_ctx)
        for call_id, r in results:
            payload = (
                str(r.content) if r.error is None else f"ERROR: {r.error}"
            )
            _slog.info("agent_tool_result", op=op_name,
                       result=payload[:800], err=r.error)
            msgs.append(
                ChatMessage(role="tool", tool_call_id=call_id, content=payload)
            )

    return _LOOP_REPLY

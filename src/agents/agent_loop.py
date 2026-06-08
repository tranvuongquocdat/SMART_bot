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

log = logging.getLogger(__name__)


_FALLBACK_REPLY = "Em xin lỗi, hệ thống đang gặp trục trặc — sếp thử lại sau ít phút."
_LOOP_REPLY = "(em xin lỗi, em hơi loạn — vui lòng thử lại)"


async def _load_prompt(prompt_key: str, ctx) -> str:
    if not prompt_key:
        return ""
    repo = PromptsRepo(ctx.db, BossContext(ctx.boss.id, "boss"))
    p = await repo.get_active(prompt_key)
    return (p.body if p else "") or ""


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
    base: set[str] = set(cfg.tools or set())
    db = getattr(ctx, "db", None)
    boss = getattr(ctx, "boss", None)
    if db is None or boss is None:
        return base
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
        return base
    enabled = {r["plugin_id"] for r in rows}
    if not enabled:
        return base
    for tname in _TOOL_REGISTRY:
        prefix = tname.split("_", 1)[0]
        if prefix in enabled:
            base.add(tname)

    # Intersect with boss's explicitly active tools.
    # Tools not present in boss_active_tools are skipped regardless of the allowlist.
    try:
        async with db.acquire() as c:
            active_rows = await c.fetch(
                "SELECT tool_name FROM boss_active_tools WHERE boss_id=$1", boss.id
            )
        boss_active = {r["tool_name"] for r in active_rows}
        if boss_active:
            base = base & boss_active
    except Exception:
        log.exception("boss_active_tools query failed — skipping filter")

    return base


def _build_tool_ctx(ctx, op_name: str) -> ToolContext:
    trace = current_trace()
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
    )


async def run_agent(op_cls, event: dict, ctx, max_iters: int = 5) -> str:
    cfg = op_cls._op_config
    op_name = cfg.name

    # 1. System prompt
    system_prompt = await _load_prompt(cfg.prompt_key, ctx)

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
                await RemindersRepo(ctx.db, boss_ctx).list(status="pending")
            )[:10]
        except Exception:
            log.exception("prospective reminders recall failed")
        try:
            action_items = (
                await ActionItemsRepo(ctx.db, boss_ctx).list_open()
            )[:10]
        except Exception:
            log.exception("prospective action_items recall failed")

    msgs: list[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content="Memory:\n"
            + _format_memory(semantic, episodic, reminders, action_items),
            name="memory_block",
        ),
        ChatMessage(role="user", content=event.get("text", "")),
    ]

    # 3. Tool surface (base allowlist + enabled plugin tools for this boss)
    allowed = await _allowed_tools(cfg, ctx)
    tools = [_to_toolspec(t) for t in registry.filter_for_op(op_name, allowed=allowed)]
    dispatcher = ToolDispatcher(ctx.db)
    tool_ctx = _build_tool_ctx(ctx, op_name=op_name)

    # 4. Loop
    for _ in range(max_iters):
        req = LLMRequest(
            feature=cfg.feature,
            messages=msgs,
            boss_id=ctx.boss.id,
            tools=tools or None,
            cache_prefix_hint=cfg.cache_prefix_hint or "after_semantic_memory",
            routing_hints={"op": op_name},
        )
        try:
            resp = await ctx.llm.complete(req)
        except Exception:
            log.exception("llm.complete raised in agent_loop")
            return _FALLBACK_REPLY

        if resp.status != "ok":
            log.warning("llm response non-ok status=%s err=%s", resp.status, resp.error)
            return resp.content or _FALLBACK_REPLY

        if not resp.tool_calls:
            return resp.content or ""

        # Append assistant turn with tool_calls (content kept as plain string).
        msgs.append(
            ChatMessage(role="assistant", content=resp.content or "")
        )
        results = await dispatcher.call_batch(resp.tool_calls, tool_ctx)
        for call_id, r in results:
            payload = (
                str(r.content) if r.error is None else f"ERROR: {r.error}"
            )
            msgs.append(
                ChatMessage(role="tool", tool_call_id=call_id, content=payload)
            )

    return _LOOP_REPLY

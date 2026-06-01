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
from src.repositories.base import BossContext
from src.repositories.prompts import PromptsRepo
from src.tools import registry
from src.tools.base import ToolContext
from src.tools.dispatcher import ToolDispatcher

log = logging.getLogger(__name__)


_FALLBACK_REPLY = "Em xin lỗi, hệ thống đang gặp trục trặc — sếp thử lại sau ít phút."
_LOOP_REPLY = "(em xin lỗi, em hơi loạn — vui lòng thử lại)"


async def _load_prompt(prompt_key: str, ctx) -> str:
    if not prompt_key:
        return ""
    repo = PromptsRepo(ctx.db, BossContext(ctx.boss.id, "boss"))
    p = await repo.get_active(prompt_key)
    return (p.body if p else "") or ""


def _format_memory(semantic, episodic) -> str:
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
    return "\n".join(lines) if lines else "(no memory)"


def _to_toolspec(td) -> ToolSpec:
    return ToolSpec(name=td.name, description=td.description, parameters=td.parameters)


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

    # 2. Memory recall (semantic + episodic when configured)
    semantic: list[Any] = []
    episodic: list[Any] = []
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

    msgs: list[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content="Memory:\n" + _format_memory(semantic, episodic),
            name="memory_block",
        ),
        ChatMessage(role="user", content=event.get("text", "")),
    ]

    # 3. Tool surface
    tools = [_to_toolspec(t) for t in registry.filter_for_op(op_name, allowed=cfg.tools)]
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

"""InGroupResponder — boss-tagged-in-group handler. Task D3."""

from dataclasses import dataclass
from typing import Any

from src.agents.agent_loop import run_agent
from src.agents.registry import operation
from src.services.outbound_service import OutboundService


@dataclass
class InGroupCtx:
    boss: Any
    memory: Any
    retriever_factory: Any
    llm: Any
    bus: Any
    db: Any
    qdrant: Any


_QUICK_ACK_TEXT = "Để em xem..."
_QUICK_ACK_THRESHOLD = 60  # chars


@operation(
    name="in_group_responder",
    triggered_by=["message.captured"],
    when=lambda e: e.get("chat_type") == "group" and e.get("mentions_bot") is True,
    deps_type=InGroupCtx,
    prompt_key="in_group",
    feature="qa_with_search",
    memory_scopes=["semantic", "episodic"],
    tools={
        "search_history",
        "read_group_note",
        "refresh_group_note",
        "find_exact_quote",
        "set_reminder",
        "list_reminders",
        "pin_message",
        "list_action_items",
        "mark_action_item",
        "fetch_url",
        "remember",
        "current_time",
    },
    timeout_s=20,
    progress_mode="quick_ack",
    cache_prefix_hint="after_group_note",
)
class InGroupResponder:
    async def handle(self, event: dict, ctx: InGroupCtx):
        text = event.get("text", "") or ""
        outbound = OutboundService(ctx.db, ctx.bus)

        # Predict-long heuristic: any tagged message > 60 chars is likely Q&A
        # that needs search → ack first so the group sees responsiveness.
        if len(text) > _QUICK_ACK_THRESHOLD:
            await outbound.send(
                boss_id=ctx.boss.id,
                provider=event["provider"],
                chat_id=event["chat_id"],
                content=_QUICK_ACK_TEXT,
                trigger="quick_ack",
            )

        answer = await run_agent(InGroupResponder, event, ctx)
        if not answer:
            return
        await outbound.send(
            boss_id=ctx.boss.id,
            provider=event["provider"],
            chat_id=event["chat_id"],
            content=answer,
            trigger="mention",
            reply_to_message_id=event.get("message_id"),
        )

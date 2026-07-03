"""DMResponder — boss DM handler. Task D1."""

from dataclasses import dataclass
from typing import Any

from src.agents.agent_loop import run_agent
from src.agents.registry import operation


@dataclass
class DMContext:
    boss: Any
    memory: Any
    retriever_factory: Any
    llm: Any
    bus: Any
    db: Any
    qdrant: Any
    outbound_service: Any


@operation(
    name="dm_responder",
    triggered_by=["message.captured"],
    when=lambda e: e.get("chat_type") == "dm" and e.get("sender_is_boss") is True,
    deps_type=DMContext,
    prompt_key="dm_general",
    feature="dm_general",
    memory_scopes=["semantic", "episodic", "prospective"],
    tools={
        "search_knowledge",
        "search_history",
        "count_messages",
        "list_groups",
        "list_reminders",
        "set_reminder",
        "cancel_reminder",
        "pin_message",
        "find_exact_quote",
        "remember",
        "forget",
        "fetch_url",
        "web_search",
        "list_action_items",
        "mark_action_item",
        "workload_summary",
        "list_members",
        "opt_out_capture",
        "edit_group_note",
        "read_group_note",
        "refresh_group_note",
        "current_time",
    },
    timeout_s=30,
    progress_mode="quick_ack",
    cache_prefix_hint="after_semantic_memory",
)
class DMResponder:
    async def handle(self, event: dict, ctx: DMContext):
        answer = await run_agent(DMResponder, event, ctx)
        if not answer:
            return
        await ctx.outbound_service.send(
            boss_id=ctx.boss.id,
            provider=event["provider"],
            chat_id=event["chat_id"],
            content=answer,
            trigger="dm",
            chat_type="dm",
        )

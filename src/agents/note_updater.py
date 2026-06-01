"""NoteUpdater — rebuild group note after debounce / threshold fires. Task D2."""

from dataclasses import dataclass
from typing import Any

from src.agents.registry import operation
from src.agents.triggers import Debounce, Threshold, trigger


@dataclass
class NoteUpdaterCtx:
    boss: Any
    db: Any
    bus: Any
    llm: Any
    memory: Any


@trigger(
    op="note_updater",
    event="message.captured",
    debounce=Debounce(key="boss_id,chat_id", window="10m"),
    threshold=Threshold(key="boss_id,chat_id", count=30),
    when=lambda e: e.get("chat_type") == "group",
)
@operation(
    name="note_updater",
    triggered_by=["op.note_updater.fire"],
    when=None,
    deps_type=NoteUpdaterCtx,
    prompt_key="note_update",
    feature="note_update",
    memory_scopes=[],
    tools=set(),
    timeout_s=120,
    progress_mode="none",
    max_concurrency_per_bot_account=1,
    cache_prefix_hint="after_system",
)
class NoteUpdater:
    async def handle(self, event: dict, ctx: NoteUpdaterCtx):
        from src.services.note_service import NoteService

        # TriggerEngine wraps the original event in {source_event: ..., reason: ...},
        # but the tool refresh_group_note publishes the source already nested too.
        # Be permissive: accept either shape.
        src = event.get("source_event") or event
        provider = src.get("provider")
        chat_id = src.get("chat_id")
        if not provider or not chat_id:
            return
        await NoteService(ctx.db, ctx.bus, ctx.llm).update(
            boss_id=ctx.boss.id,
            provider=provider,
            chat_id=chat_id,
        )

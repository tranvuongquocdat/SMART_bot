"""KnowledgeExtractor — write-pipeline operation: extract→reconcile khi nhóm có tin mới.

Cùng cadence note_updater (debounce 10m / threshold 30 tin, chỉ group). Chạy KnowledgeService
(EXTRACT→RECONCILE→KnowledgeRepo) + KnowledgeIndex (embed→Qdrant) trên delta kể từ
last_extracted_message_id (cursor riêng, tách khỏi note).
"""

from dataclasses import dataclass
from typing import Any

from src.agents.registry import operation
from src.agents.triggers import Debounce, Threshold, trigger


@dataclass
class KnowledgeExtractorCtx:
    boss: Any
    db: Any
    bus: Any
    llm: Any
    qdrant: Any


@trigger(
    op="knowledge_extract",
    event="message.captured",
    debounce=Debounce(key="boss_id,chat_id", window="10m"),
    threshold=Threshold(key="boss_id,chat_id", count=30),
    when=lambda e: e.get("chat_type") == "group",
)
@operation(
    name="knowledge_extract",
    triggered_by=["op.knowledge_extract.fire"],
    when=None,
    deps_type=KnowledgeExtractorCtx,
    prompt_key="knowledge_extract",
    feature="knowledge_extract",
    memory_scopes=[],
    tools=set(),
    timeout_s=120,
    progress_mode="none",
    max_concurrency_per_bot_account=1,
    cache_prefix_hint="after_system",
)
class KnowledgeExtractor:
    async def handle(self, event: dict, ctx: KnowledgeExtractorCtx):
        from src.memory.knowledge_index import KnowledgeIndex
        from src.repositories.base import BossContext
        from src.repositories.group_notes import GroupNotesRepo
        from src.services.knowledge_service import KnowledgeService
        from src.services.subscription import is_group_active

        src = event.get("source_event") or event
        provider = src.get("provider")
        chat_id = src.get("chat_id")
        if not provider or not chat_id:
            return
        if not await is_group_active(ctx.db, ctx.boss.id, provider, chat_id):
            return  # nhóm bị tắt trên web admin

        repo = GroupNotesRepo(ctx.db, BossContext(ctx.boss.id, "boss"))
        await repo.get_or_create(provider, chat_id)  # đảm bảo row tồn tại
        after = await repo.get_last_extracted(provider, chat_id)

        index = KnowledgeIndex(ctx.db, ctx.qdrant, ctx.llm)
        svc = KnowledgeService(ctx.db, ctx.llm, index=index)
        res = await svc.process(ctx.boss.id, provider, chat_id, after_message_id=after)

        last = res.get("last_message_id")
        if last:
            await repo.set_last_extracted(provider, chat_id, last)

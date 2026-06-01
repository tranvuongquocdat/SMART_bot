"""NoteService — owns rebuild / pin / edit-section flows for group notes.

Used by:
- Task D2 NoteUpdater operation (rebuild on debounce / threshold fire)
- Task D0 tools: refresh_group_note, edit_group_note, pin_message
"""

import asyncio
import json
import logging

from src.llm.base import ChatMessage, LLMRequest
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.messages import MessagesRepo
from src.repositories.note_templates import NoteTemplatesRepo
from src.repositories.pins import PinsRepo
from src.repositories.prompts import PromptsRepo

log = logging.getLogger(__name__)


class NoteService:
    def __init__(self, pool, bus, llm):
        self.pool = pool
        self.bus = bus
        self.llm = llm
        # Per-(boss, provider, chat) lock to serialize concurrent rebuilds.
        self._locks: dict[tuple, asyncio.Lock] = {}

    def _lock_for(self, boss_id: int, provider: str, chat_id: str) -> asyncio.Lock:
        key = (boss_id, provider, chat_id)
        lk = self._locks.get(key)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[key] = lk
        return lk

    async def update(self, boss_id: int, provider: str, chat_id: str) -> int | None:
        """Rebuild the group note for (boss, provider, chat) using delta messages.

        Returns the new group_note_versions.id on success, or None when there
        are no new messages to digest.
        """
        async with self._lock_for(boss_id, provider, chat_id):
            ctx = BossContext(boss_id, "boss")
            notes = GroupNotesRepo(self.pool, ctx)
            tmpl_repo = NoteTemplatesRepo(self.pool, ctx)
            messages = MessagesRepo(self.pool, ctx)
            prompts = PromptsRepo(self.pool, ctx)

            note = await notes.get_or_create(provider, chat_id)
            template = None
            tid = note.template_id or await tmpl_repo.system_default_id()
            if tid is not None:
                template = await tmpl_repo.get(tid)

            delta = await messages.fetch_after_id(
                chat_id, note.last_seen_message_id or 0, limit=200
            )
            if not delta:
                return None

            sections_json = json.dumps(
                template.sections_json if template else [], ensure_ascii=False
            )
            delta_text = "\n".join(
                f"[{m.id}] {m.sender_name or '?'}: {m.text or ''}" for m in delta
            )

            prompt = await prompts.get_active("note_update")
            system_body = prompt.body if prompt else ""
            # Plain string interpolation — prompt bodies are Jinja-style but we
            # use simple template variables here to avoid pulling Jinja for
            # MVP. If complex syntax is needed, swap to jinja2.Template.
            rendered = (
                system_body.replace("{{ sections_json }}", sections_json)
                .replace("{{ current_markdown }}", note.content or "")
                .replace("{{ template_json }}", sections_json)
                .replace("{{ current_note }}", note.content or "")
                .replace("{{ delta }}", delta_text)
                .replace("{{ recent_messages }}", delta_text)
            )

            req = LLMRequest(
                feature="note_update",
                boss_id=boss_id,
                messages=[ChatMessage(role="system", content=rendered)],
                cache_prefix_hint="after_system",
                routing_hints={"op": "note_updater"},
            )
            resp = await self.llm.complete(req)
            new_content = (resp.content or note.content) if resp else note.content

            version_id = await notes.update_after_note_rebuild(
                group_note_id=note.id,
                content=new_content,
                last_seen_message_id=delta[-1].id,
                emitted_by="note_updater",
            )
            await self.bus.publish(
                "note.updated",
                {
                    "group_note_id": note.id,
                    "boss_id": boss_id,
                    "version_id": version_id,
                    "sections_changed": [],
                },
            )
            return version_id

    async def edit_section(
        self,
        boss_id: int,
        chat_id: str,
        section_key: str,
        new_content: str,
        by: str,
    ) -> None:
        """MVP edit_section: locate note by chat_id, mark section as manually edited,
        and append/replace the section in note.content as a fenced markdown block.

        Full template-aware section replacement is deferred to a richer
        renderer; for MVP this preserves the agent contract: "edit_group_note
        returns ok and the change is persisted (versioned)."
        """
        ctx = BossContext(boss_id, "boss")
        notes = GroupNotesRepo(self.pool, ctx)
        note = await notes.get_by_chat(chat_id)
        if note is None:
            raise LookupError(f"group_note for chat_id={chat_id} not found")

        marker_start = f"<!-- section:{section_key} -->"
        marker_end = f"<!-- /section:{section_key} -->"
        section_block = f"{marker_start}\n{new_content}\n{marker_end}"

        content = note.content or ""
        if marker_start in content and marker_end in content:
            head, _, rest = content.partition(marker_start)
            _, _, tail = rest.partition(marker_end)
            new_full = f"{head}{section_block}{tail}"
        else:
            sep = "\n\n" if content else ""
            new_full = f"{content}{sep}{section_block}"

        # Track as manually edited.
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE group_notes
                SET manually_edited_sections = (
                  SELECT COALESCE(jsonb_agg(DISTINCT x), '[]'::jsonb)
                  FROM jsonb_array_elements_text(
                      COALESCE(manually_edited_sections, '[]'::jsonb)
                      || to_jsonb($3::TEXT)
                  ) AS x
                )
                WHERE id=$1 AND boss_id=$2
                """,
                note.id,
                boss_id,
                section_key,
            )
        await notes.update_after_note_rebuild(
            group_note_id=note.id,
            content=new_full,
            last_seen_message_id=note.last_seen_message_id or 0,
            emitted_by=by,
        )

    async def pin(
        self, boss_id: int, message_id: int, note: str | None = None
    ) -> int:
        """Pin a message into its chat's group_note. Returns pin id."""
        ctx = BossContext(boss_id, "boss")
        messages = MessagesRepo(self.pool, ctx)
        notes_repo = GroupNotesRepo(self.pool, ctx)
        msg = await messages.get(message_id)
        if msg is None:
            raise LookupError(f"message {message_id} not found")
        gnote = await notes_repo.get_or_create(msg.provider, msg.chat_id)
        pins = PinsRepo(self.pool, ctx)
        return await pins.insert(
            group_note_id=gnote.id,
            message_id=message_id,
            pinned_by=boss_id,
            note=note,
        )

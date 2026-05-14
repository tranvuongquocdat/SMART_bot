"""Single chokepoint for `memberships.status='active'` writes.

Every code path that needs to grant active membership goes through `activate()`.
No other module should call `repo.upsert(..., status='active')` directly."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from src import db
from src.channels import telegram_singleton as telegram
from src.infrastructure import lark_client as lark
from src.repositories.membership_repo import MembershipRepo

logger = logging.getLogger("services.membership")

Source = Literal["approval", "boss_add", "self_boss", "link_contact"]


async def activate(
    *,
    chat_id: str,
    boss_chat_id: str,
    person_type: str,
    name: str,
    source: Source,
    lark_record_id: Optional[str] = None,
    request_info: Optional[str] = None,
) -> None:
    """Promote a person to active membership in a workspace. Single write path.

    - If the prior row was status='pending', send the approved-user
      notification regardless of `source` (semantically an approval).
    - Upsert Lark People if `lark_record_id` is None.
    - Emit one audit log line tagged with `source`.
    """
    _db = await db.get_db()
    repo = MembershipRepo(_db)

    prior = await repo.get(str(chat_id), str(boss_chat_id))
    was_pending = bool(prior and prior.get("status") == "pending")

    rec_id = lark_record_id
    if not rec_id:
        boss = await db.get_boss(str(boss_chat_id))
        if boss and boss.get("lark_base_token") and boss.get("lark_table_people"):
            ext = await db.lookup_external_for_person(chat_id)
            chat_id_for_lark = int(ext[1]) if ext and ext[1].isdigit() else 0
            fields = {
                "Tên": name,
                "Chat ID": chat_id_for_lark,
                "Type": person_type,
                "Ghi chú": request_info or "",
            }
            try:
                created = await lark.create_record(
                    boss["lark_base_token"], boss["lark_table_people"], fields,
                )
                rec_id = created.get("record_id", "")
            except Exception:
                logger.warning(
                    "lark People upsert failed for chat_id=%s", chat_id, exc_info=True,
                )

    await repo.upsert(
        str(chat_id), str(boss_chat_id), person_type, name,
        status="active", request_info=request_info, lark_record_id=rec_id,
    )

    if was_pending:
        boss = await db.get_boss(str(boss_chat_id))
        company = (boss or {}).get("company") or (boss or {}).get("name", "the workspace")
        try:
            await telegram.send(
                str(chat_id),
                f"Your request to join {company} has been approved as {person_type}. "
                f"You can now interact with the AI secretary.",
            )
        except Exception:
            logger.warning(
                "approved-user notification failed for chat_id=%s", chat_id, exc_info=True,
            )

    logger.info(
        "membership.activate source=%s chat_id=%s boss=%s type=%s",
        source, chat_id, boss_chat_id, person_type,
    )

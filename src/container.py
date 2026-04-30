"""AppContainer — explicit dependency wiring built once during FastAPI lifespan.

Phase 5a ships the dataclass + builder. Phase 5b's `MessageRouter` is the first
real consumer; existing module-level singletons (`db._db`, `_dispatcher` in
`src.agent`, etc.) keep working until 5b reroutes them.

Construction order, enforced by the builder, mirrors the layered dependency
arrows: infrastructure → repos → channels → services → agents → controllers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import aiosqlite

from src import db as _db_mod
from src.config import Settings
from src.repositories.audit_repo import AuditRepo
from src.repositories.boss_repo import BossRepo
from src.repositories.identity_repo import IdentityRepo
from src.repositories.conversation_repo import ConversationRepo
from src.repositories.membership_repo import MembershipRepo
from src.repositories.message_repo import MessageRepo
from src.repositories.note_repo import NoteRepo
from src.repositories.reminder_repo import ReminderRepo
from src.repositories.token_usage_repo import TokenUsageRepo
from src.repositories.session_repo import SessionRepo
from src.repositories.approval_repo import ApprovalRepo
from src.repositories.review_repo import ReviewRepo
from src.services.audit_service import AuditService

if TYPE_CHECKING:
    from src.channels.base import BaseMessenger


@dataclass(frozen=True)
class AppContainer:
    """Frozen wiring snapshot. Built once, read everywhere."""

    settings: Settings
    db: aiosqlite.Connection

    # Repositories
    boss_repo: BossRepo
    identity_repo: IdentityRepo
    conversation_repo: ConversationRepo
    membership_repo: MembershipRepo
    message_repo: MessageRepo
    note_repo: NoteRepo
    reminder_repo: ReminderRepo
    token_usage_repo: TokenUsageRepo
    session_repo: SessionRepo
    approval_repo: ApprovalRepo
    review_repo: ReviewRepo
    audit_repo: AuditRepo

    # Services (Phase 5a ships only AuditService; rest still module-level)
    audit_service: AuditService

    # Channels (provider name → messenger). Populated by main.py lifespan.
    messengers: dict[str, "BaseMessenger"] = field(default_factory=dict)


async def build_container(settings: Settings) -> AppContainer:
    """Build the container with all known wiring. The connection is opened
    via `db.get_db` so the existing singleton + facade keeps working."""
    db = await _db_mod.get_db(settings.db_path)

    # Repositories.
    boss_repo         = BossRepo(db)
    identity_repo     = IdentityRepo(db)
    conversation_repo = ConversationRepo(db)
    membership_repo   = MembershipRepo(db)
    message_repo      = MessageRepo(db)
    note_repo         = NoteRepo(db)
    reminder_repo     = ReminderRepo(db)
    token_usage_repo  = TokenUsageRepo(db)
    session_repo      = SessionRepo(db)
    approval_repo     = ApprovalRepo(db)
    review_repo       = ReviewRepo(db)
    audit_repo        = AuditRepo(db)

    # Services.
    audit_service = AuditService(audit_repo)

    return AppContainer(
        settings=settings,
        db=db,
        boss_repo=boss_repo,
        identity_repo=identity_repo,
        conversation_repo=conversation_repo,
        membership_repo=membership_repo,
        message_repo=message_repo,
        note_repo=note_repo,
        reminder_repo=reminder_repo,
        token_usage_repo=token_usage_repo,
        session_repo=session_repo,
        approval_repo=approval_repo,
        review_repo=review_repo,
        audit_repo=audit_repo,
        audit_service=audit_service,
        messengers={},
    )

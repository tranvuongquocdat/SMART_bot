from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BotAccountOwnership(StrEnum):
    PLATFORM = "platform"
    BOSS_OWNED = "boss_owned"


class BotAccountStatus(StrEnum):
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"
    BANNED = "banned"
    RATE_LIMITED = "rate_limited"
    PAUSED = "paused"


class AssignmentStatus(StrEnum):
    PENDING_ACCEPT = "pending_accept"
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class BotAccount:
    id: int
    provider: str
    provider_user_id: str
    display_name: str | None
    account_kind: str
    ownership: BotAccountOwnership
    owner_boss_id: int | None
    status: BotAccountStatus
    status_reason: str | None
    max_assigned_bosses: int
    msgs_received_total: int
    msgs_sent_total: int
    last_seen_at: datetime | None
    notes: str | None
    # credentials_blob_enc intentionally excluded — dispenser-internal only


@dataclass(frozen=True, slots=True)
class BotAccountAssignment:
    boss_id: int
    provider: str
    bot_account_id: int
    assignment_kind: str
    status: AssignmentStatus
    assigned_at: datetime
    assigned_by: int | None
    accepted_at: datetime | None

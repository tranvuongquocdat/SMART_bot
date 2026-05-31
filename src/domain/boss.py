from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class UserRole(StrEnum):
    BOSS = "boss"
    SUPERADMIN = "superadmin"


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class Boss:
    id: int
    email: str
    name: str | None
    role: str
    tz: str
    language: str
    smart_model_id: int | None
    fast_model_id: int | None
    vision_model_id: int | None
    subscription_status: str
    subscription_expiry: datetime | None
    cost_cap_usd_daily: float

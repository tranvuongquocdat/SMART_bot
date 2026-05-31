from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ModelTier(StrEnum):
    SMART = "smart"
    FAST = "fast"
    VISION = "vision"


class EndpointKind(StrEnum):
    OPENAI_COMPAT = "openai_compat"
    GEMINI = "gemini"


@dataclass(frozen=True, slots=True)
class Model:
    id: int
    name: str
    provider: str
    endpoint_kind: str
    base_url: str | None
    tier: str
    ctx_max: int
    capabilities: list[str] = field(default_factory=list)
    cost_per_1m_input_usd: Decimal | None = None
    cost_per_1m_output_usd: Decimal | None = None
    is_platform_default: bool = False
    is_active: bool = True
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LLMRoute:
    id: int
    feature: str
    condition_cel: str | None
    target_tier: str
    fallback_chain: list[dict[str, Any]]
    weight: int
    is_active: bool
    notes: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class FeatureBudget:
    feature: str
    max_input_tokens: int
    max_output_tokens: int
    trim_policy_json: list[str]
    compression_strategy: str
    cache_prefix_hint: str | None
    updated_at: datetime | None

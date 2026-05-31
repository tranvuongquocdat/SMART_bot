from dataclasses import dataclass
from typing import Any, Callable, Protocol, Type

from src.events.schema import BaseEvent


@dataclass
class OpConfig:
    name: str
    triggered_by: list[str]
    when: Callable[[BaseEvent], bool] | None
    deps_type: Type
    prompt_key: str
    feature: str
    memory_scopes: list[str]
    tools: set[str]
    timeout_s: int
    progress_mode: str  # 'none' | 'quick_ack'
    max_concurrency_per_bot_account: int
    cache_prefix_hint: str | None


class Operation(Protocol):
    _op_config: OpConfig

    async def handle(self, event: Any, ctx: Any) -> Any: ...

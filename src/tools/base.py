from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class ToolContext:
    boss_id: int
    boss_role: str
    pool: Any  # asyncpg.Pool
    qdrant: Any
    bus: Any
    memory: Any  # MemoryProvider
    retriever_factory: Any  # callable(feature) -> RetrievalPipeline
    llm: Any  # LLMGateway
    trace_id: str
    span_id: str


@dataclass
class ToolResult:
    content: Any
    error: str | None = None


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    feature: str | None
    cost_class: str
    available_to: set[str]
    rate_limit: str | None
    timeout_s: int
    parallel_safe: bool
    handler: Callable[..., Awaitable[ToolResult]]

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
    # Bối cảnh hội thoại hiện tại (để tool scope đúng nơi đang nói — vd
    # search_knowledge mặc định chỉ tra nhóm hiện tại thay vì mọi nhóm của sếp).
    chat_id: str | None = None
    provider: str | None = None
    chat_type: str | None = None  # "group" | "dm"


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

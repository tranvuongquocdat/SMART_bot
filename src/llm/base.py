from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict]
    name: str | None = None
    tool_call_id: str | None = None
    cache_breakpoint: bool = False


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMRequest:
    feature: str
    messages: list[ChatMessage]
    boss_id: int
    tools: list[ToolSpec] | None = None
    required_caps: set[str] = field(default_factory=set)
    routing_hints: dict = field(default_factory=dict)
    cache_prefix_hint: str | None = None
    max_output_tokens: int | None = None
    temperature: float = 0.7


@dataclass
class LLMUsage:
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    latency_ms: int
    model: str
    provider: str


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: LLMUsage
    status: Literal["ok", "error", "rate_limited"]
    error: str | None = None


class LLMGateway(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

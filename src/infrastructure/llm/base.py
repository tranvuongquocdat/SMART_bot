"""Provider-agnostic LLM client Protocol.

Implementations live in this package (`openai.py`, future `groq.py`,
`gemini.py`, `anthropic.py`). Services depend on this Protocol — never on
a concrete provider — so swapping providers per boss is a constructor
choice, not a refactor.

Shape rationale:
- `chat_with_tools` returns the same shape today's `infrastructure.openai_client`
  returns (a (response, usage_dict) tuple). Phase 4b wraps tool-call routing
  on top so the surface to services is uniform across providers later.
- `embed` returns (vector, dim) so callers (Qdrant naming, capacity checks)
  see the dim in-band rather than reading it from a global setting.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """A configured LLM provider client. Holds credentials + model choices."""

    @property
    def chat_model(self) -> str: ...

    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_dim(self) -> int: ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """Run a chat completion with tools. Returns (response, usage)."""
        ...

    async def embed(self, text: str) -> tuple[list[float], int]:
        """Return (embedding_vector, dim)."""
        ...

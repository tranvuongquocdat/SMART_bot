"""ToolHandler base — every LLM-facing tool implements this Protocol.

Phase 4b-2 services + handlers concrete patterns. The base intentionally
keeps the contract minimal so handlers can vary in how they parse args /
format errors / inject services.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.context import ChatContext


@runtime_checkable
class ToolHandler(Protocol):
    """A single LLM-facing tool. The dispatcher resolves by `name`."""

    name: str

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        """Execute the tool. Returns string for the LLM to read.

        Conventions for the returned string:
        - Success: human-readable summary, e.g., `"Đã tạo task 'foo'."`.
        - Recoverable failure: `[TOOL_ERROR:<code>] <reason>` so the LLM
          can decide a fallback. The dispatcher wraps unhandled exceptions
          in `[TOOL_ERROR:unknown]` automatically.
        """
        ...

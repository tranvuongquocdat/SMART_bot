"""ToolDispatcher — name → handler registry with legacy fallback.

For Phase 4b-1 only a handful of handlers are migrated. Unknown names
delegate to `src.tools.execute_tool` (the legacy `match`-statement
dispatcher) so the bot keeps working end-to-end. Phase 4b-2 mass-migrates
the rest; once every tool has a handler, the fallback can be removed and
`src.tools` deleted entirely (Phase 4b-2 done criterion).
"""
from __future__ import annotations

import json
import logging

from src.agent.handlers._base import ToolHandler
from src.context import ChatContext

logger = logging.getLogger("agent.dispatcher")


class ToolDispatcher:
    def __init__(self, handlers: list[ToolHandler]) -> None:
        self._by_name: dict[str, ToolHandler] = {}
        for h in handlers:
            if h.name in self._by_name:
                raise ValueError(f"duplicate handler name: {h.name!r}")
            self._by_name[h.name] = h

    @property
    def known_names(self) -> set[str]:
        return set(self._by_name.keys())

    async def execute(
        self, name: str, arguments: str | dict, ctx: ChatContext,
    ) -> str:
        handler = self._by_name.get(name)
        if handler is None:
            return f"Tool '{name}' không tồn tại."

        try:
            args = self._parse_args(arguments)
        except json.JSONDecodeError as e:
            logger.warning("Bad JSON args for %s: %s", name, e)
            return f"[TOOL_ERROR:bad_args] {name}: invalid JSON"

        try:
            return await handler.handle(args, ctx)
        except Exception as exc:  # noqa: BLE001  — uniform error envelope
            return self._format_error(name, exc)

    @staticmethod
    def _format_error(name: str, exc: Exception) -> str:
        """Classify common errors so the LLM gets a recoverable hint.

        Mirrors the legacy `tools.execute_tool` error envelope so prompt
        instructions about `[TOOL_ERROR:lark]` / `[TOOL_ERROR:not_found]`
        keep working unchanged.
        """
        err_type = type(exc).__name__
        msg = str(exc)
        low = msg.lower()
        if any(kw in low for kw in ("lark", "base_token", "table", "record")):
            return (
                f"[TOOL_ERROR:lark] {name} — Lark không phản hồi hoặc cấu hình sai: {msg}. "
                f"Thử lại hoặc báo người dùng."
            )
        if any(kw in low for kw in ("not found", "không tìm thấy", "no such")):
            return (
                f"[TOOL_ERROR:not_found] {name} — {msg}. "
                f"Hãy hỏi lại người dùng tên chính xác."
            )
        return f"[TOOL_ERROR:unknown] {name} thất bại ({err_type}): {msg}"

    @staticmethod
    def _parse_args(arguments: str | dict) -> dict:
        if isinstance(arguments, dict):
            return arguments
        return json.loads(arguments)

"""escalate_to_advisor handler — returns the sentinel `__ESCALATE__`.

`agent.py` reads this string to switch the LLM loop to the advisor agent.
The handler holds no logic; the sentinel is part of the agent contract.
"""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext


class EscalateToAdvisorHandler(ToolHandler):
    name = "escalate_to_advisor"

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return "__ESCALATE__"

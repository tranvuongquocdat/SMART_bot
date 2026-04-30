"""Compat shim — body lives at `src.agent_pkg.advisor_agent` after Phase 4b-3.

Existing callers (scheduler, agent.py escalation flow) import from `src.advisor`.
Phase 5 will update those callers and delete this shim.
"""
from src.agent_pkg.advisor_agent import (  # noqa: F401
    ADVISOR_PROMPT,
    ADVISOR_TOOLS,
    DAILY_REVIEW_PROMPT,
    MAX_TOOL_ROUNDS,
    run_advisor,
    run_daily_review,
)

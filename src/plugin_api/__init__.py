"""Public surface for plugin authors.

Plugins import from ``src.plugin_api`` (and only from here) to declare
tools. This insulates plugin code from internal layout changes —
re-export `@tool`, `ToolContext`, and `ToolResult` from the canonical
locations.
"""

from src.tools.base import ToolContext, ToolResult
from src.tools.registry import tool

__all__ = ["tool", "ToolContext", "ToolResult"]

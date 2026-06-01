"""Strip Markdown formatting tokens for outbound text on Zalo.

Zalo's native renderer doesn't support Markdown — emoji, raw text and URLs
are fine but ``**bold**`` / ``__italic__`` / ``# heading`` would show as
literal characters. We keep this tiny and safe (no full parser).
"""

from __future__ import annotations

import re

_RE_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_RE_BOLD_AST = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_RE_BOLD_UND = re.compile(r"__(.+?)__", re.DOTALL)
_RE_ITAL_AST = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)
_RE_ITAL_UND = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", re.DOTALL)
_RE_CODE_INL = re.compile(r"`([^`]+)`")
_RE_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n([\s\S]*?)```", re.MULTILINE)
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_BULLET = re.compile(r"^[ \t]*[-*+][ \t]+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    if not text:
        return text
    s = text
    s = _RE_CODE_FENCE.sub(lambda m: m.group(1), s)
    s = _RE_LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", s)
    s = _RE_HEADING.sub("", s)
    s = _RE_BOLD_AST.sub(lambda m: m.group(1), s)
    s = _RE_BOLD_UND.sub(lambda m: m.group(1), s)
    s = _RE_ITAL_AST.sub(lambda m: m.group(1), s)
    s = _RE_ITAL_UND.sub(lambda m: m.group(1), s)
    s = _RE_CODE_INL.sub(lambda m: m.group(1), s)
    s = _RE_BULLET.sub("- ", s)
    return s

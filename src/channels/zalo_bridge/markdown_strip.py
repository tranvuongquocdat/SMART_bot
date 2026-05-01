"""Convert markdown-flavored text to Zalo-friendly plain text.

Zalo's chat doesn't render markdown, so users see literal `**`, `#`, backticks,
etc. The agent's prompts produce markdown by default; we strip it at egress.
"""
from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
_HRULE_RE = re.compile(r"^[\-_*]{3,}\s*$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*|__([^_\n]+)__")
_ITALIC_RE = re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)")
_BULLET_RE = re.compile(r"^([ \t]*)[-*+]\s+", re.MULTILINE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def markdown_to_plain(text: str) -> str:
    if not text:
        return text

    fences: list[str] = []

    def _stash_fence(m: re.Match) -> str:
        fences.append(m.group(1).rstrip("\n"))
        return f"\x00FENCE{len(fences) - 1}\x00"

    text = _CODE_FENCE_RE.sub(_stash_fence, text)
    text = _HEADER_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _HRULE_RE.sub("", text)
    text = _IMAGE_RE.sub(lambda m: m.group(2), text)

    def _link(m: re.Match) -> str:
        label, url = m.group(1).strip(), m.group(2).strip()
        return url if label == url else f"{label} ({url})"

    text = _LINK_RE.sub(_link, text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = _BULLET_RE.sub(lambda m: f"{m.group(1)}• ", text)

    for i, content in enumerate(fences):
        text = text.replace(f"\x00FENCE{i}\x00", content)

    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()

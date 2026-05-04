"""Whole-line sentinel parsing for file refs in messages.content.

Format (each on its own line):
  [OPENAI_FILE: file_id=file-xxx mime=application/pdf filename=invoice.pdf]
  [LOCAL_IMAGE: path=data/inbound/abc/123_photo.jpg mime=image/jpeg]

Used by:
  • file_ingestion — emit sentinels for files attached to user message
  • infrastructure/llm/openai.py — convert sentinels to content parts at LLM call
  • Qdrant indexer — strip sentinels before embedding so RAG stays clean
"""
from __future__ import annotations

import re
from typing import NamedTuple

_SENTINEL_RE = re.compile(
    r"^\[(OPENAI_FILE|LOCAL_IMAGE):\s+(.+)\]$",
    re.MULTILINE,
)
_KV_RE = re.compile(r"(\w+)=(\S+)")


class SentinelRef(NamedTuple):
    kind: str
    fields: dict[str, str]


def strip_sentinels(text: str) -> str:
    """Remove whole-line sentinels; leave inline-typed lookalikes alone."""
    if not text:
        return text
    cleaned = _SENTINEL_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def parse_sentinels(text: str) -> tuple[str, list[SentinelRef]]:
    """Return (cleaned_text, refs)."""
    if not text:
        return text, []
    refs: list[SentinelRef] = []
    for m in _SENTINEL_RE.finditer(text):
        fields = dict(_KV_RE.findall(m.group(2)))
        refs.append(SentinelRef(kind=m.group(1), fields=fields))
    return strip_sentinels(text), refs

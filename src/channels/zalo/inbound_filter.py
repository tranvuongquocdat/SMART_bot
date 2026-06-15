"""Filter rules for raw Zalo inbound payloads before normalization.

Drop:
  - forwarded messages we don't want to capture
  - empty messages (no text + no media_url)

Inputs are the normalized dict produced by ``bridge.js``.
"""

from __future__ import annotations

from typing import Any


def should_drop(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return True
    # forwarded messages — for MVP we keep behavior conservative and DO
    # ingest forwards (treat them like normal). Flip to True if we ever
    # decide they cause noise in note synthesis.
    # if data.get("is_forwarded"):
    #     return True
    text = (data.get("text") or data.get("content") or "")
    if not isinstance(text, str):
        text = ""
    has_media = bool(data.get("media_url"))
    has_attachments = bool(data.get("attachments"))
    if not text.strip() and not has_media and not has_attachments:
        return True
    return False


def should_drop_normalized(msg) -> bool:
    """Như should_drop nhưng cho InboundMessage đã chuẩn hoá (dùng bởi InboundIngest)."""
    text = (msg.text or "").strip()
    if not text and not msg.media_url:
        return True
    return False

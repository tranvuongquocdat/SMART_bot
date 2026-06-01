"""Per-provider capability matrix.

Used by callers (group note flusher, admin web) to decide whether a feature
applies for a given channel without sniffing provider strings.
"""

from __future__ import annotations

from typing import Any

ZALO_CAPS: dict[str, Any] = {
    "inbound.has_webhook": False,
    "inbound.supports_groups": True,
    "inbound.supports_mentions": True,
    "inbound.media_kinds": ["text", "image", "file", "voice", "sticker", "url"],
    "outbound.send_text": True,
    "outbound.reply_to_msg": True,
    "outbound.send_file": True,
    "outbound.typing_indicator": True,
    "member.list_api": "partial",
    "auth.kind": "personal_cookies",
    "requires_admin_role_for_core": False,
}


CAPABILITIES: dict[str, dict[str, Any]] = {
    "zalo": ZALO_CAPS,
}


def caps_for(provider: str) -> dict[str, Any]:
    return CAPABILITIES.get(provider, {})

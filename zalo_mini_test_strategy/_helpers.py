"""Shared helpers — session load/save + a probe-friendly imei.

`zlapi` requires a stable `imei`. We hard-code one for the probe folder
(it's only ever used by you, on your account).
"""
from __future__ import annotations

import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SESSION_PATH = HERE / "session.json"

# Fixed-but-arbitrary imei. zlapi just needs it to be stable across runs so
# Zalo treats us as the same device. Don't change after first login or
# you'll be back to phone-OTP territory.
PROBE_IMEI = os.environ.get("ZALO_PROBE_IMEI", "00000000-0000-0000-0000-000000000001")


def load_session() -> dict | None:
    if not SESSION_PATH.exists():
        return None
    try:
        return json.loads(SESSION_PATH.read_text())
    except json.JSONDecodeError:
        return None


def save_session(cookies: dict) -> None:
    SESSION_PATH.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))
    print(f"[session] saved → {SESSION_PATH}")

"""Probe 1 — first-time login. Saves session cookies for the rest of the probes.

Usage:
    ZALO_PHONE=+84xxx ZALO_PASSWORD=xxx uv run python zalo_mini_test_strategy/probe_login.py

Re-run is safe: if a `session.json` already exists, this script tries to
reuse it (cookie login) and only falls back to password if cookies don't
work. Output to stdout: your own user_id once login succeeds.
"""
from __future__ import annotations

import os
import sys

from zlapi import ZaloAPI

from _helpers import PROBE_IMEI, SESSION_PATH, load_session, save_session


def main() -> int:
    phone = os.environ.get("ZALO_PHONE", "")
    password = os.environ.get("ZALO_PASSWORD", "")

    cookies = load_session()
    if cookies:
        print("[login] reusing saved session…")
        try:
            client = ZaloAPI(
                imei=PROBE_IMEI, phone=phone, password=password,
                session_cookies=cookies,
            )
            print(f"[login] OK · user_id = {client.user_id}")
            # Refresh saved cookies in case they rotated.
            save_session(client.getCookies() if hasattr(client, "getCookies") else cookies)
            return 0
        except Exception as exc:
            print(f"[login] cookie session failed: {exc}\n         falling back to password login…")

    if not phone or not password:
        print("ERR: set ZALO_PHONE and ZALO_PASSWORD env vars for first-time login.", file=sys.stderr)
        return 2

    client = ZaloAPI(imei=PROBE_IMEI, phone=phone, password=password)
    print(f"[login] OK · user_id = {client.user_id}")

    cookies = client.getCookies() if hasattr(client, "getCookies") else None
    if not cookies:
        # Older zlapi: cookies may live on `_state` — fish them out best-effort.
        cookies = getattr(client, "_state", None)
        cookies = getattr(cookies, "_session", {}).cookies.get_dict() if cookies else {}
    save_session(cookies)
    print(f"[login] session saved → {SESSION_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

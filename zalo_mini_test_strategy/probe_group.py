"""Probe 4 — group fetch + members.

Usage:
    uv run python zalo_mini_test_strategy/probe_group.py
    uv run python zalo_mini_test_strategy/probe_group.py <group_id>

Without args: lists every group the account is in.
With a group_id: prints that group's info + member list (truncated to 20).
"""
from __future__ import annotations

import json
import os
import sys

from zlapi import ZaloAPI

from _helpers import PROBE_IMEI, load_session


def main(argv: list[str]) -> int:
    cookies = load_session()
    if not cookies:
        print("ERR: no session.json — run probe_login.py first.", file=sys.stderr)
        return 2

    phone = os.environ.get("ZALO_PHONE", "")
    password = os.environ.get("ZALO_PASSWORD", "")
    client = ZaloAPI(
        imei=PROBE_IMEI, phone=phone, password=password,
        session_cookies=cookies,
    )

    if len(argv) < 2:
        print("[groups] fetching all…")
        try:
            groups = client.fetchAllGroups()
            print(f"[groups] fetchAllGroups returned type={type(groups).__name__}")
            print(json.dumps(groups, default=str, indent=2, ensure_ascii=False)[:4000])
        except Exception as exc:
            print(f"[groups] ERR: {exc}")
        return 0

    group_id = argv[1]
    print(f"[group {group_id}] fetching info…")
    try:
        info = client.fetchGroupInfo(group_id)
        print(json.dumps(info, default=str, indent=2, ensure_ascii=False)[:4000])
    except Exception as exc:
        print(f"[group {group_id}] ERR: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Probe 3 — outbound send.

Usage (DM to self):
    uv run python zalo_mini_test_strategy/probe_send.py self "hello from probe"

Usage (send to a specific user/group ID):
    uv run python zalo_mini_test_strategy/probe_send.py user 1234567890 "hi"
    uv run python zalo_mini_test_strategy/probe_send.py group 9876543210 "hi team"

Get user/group IDs by running probe_listen.py first — they print there.
"""
from __future__ import annotations

import os
import sys

from zlapi import ZaloAPI, Message, ThreadType

from _helpers import PROBE_IMEI, load_session


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    target_kind, target_id, text = argv[1], argv[2], " ".join(argv[3:])
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

    if target_kind == "self":
        thread_id = client.user_id
        thread_type = ThreadType.USER
    elif target_kind == "user":
        thread_id = target_id
        thread_type = ThreadType.USER
    elif target_kind == "group":
        thread_id = target_id
        thread_type = ThreadType.GROUP
    else:
        print(f"ERR: target_kind must be self|user|group, got {target_kind!r}", file=sys.stderr)
        return 2

    print(f"[send] → {target_kind} {thread_id}: {text!r}")
    msg = Message(text=text)
    result = client.send(msg, thread_id=thread_id, thread_type=thread_type)
    print(f"[send] result: {result!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

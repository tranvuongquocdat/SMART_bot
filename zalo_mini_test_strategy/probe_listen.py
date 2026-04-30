"""Probe 2 — listener. Prints every incoming message zlapi surfaces.

Usage:
    ZALO_PHONE=+84xxx ZALO_PASSWORD=xxx uv run python zalo_mini_test_strategy/probe_listen.py

While running, send your account a few messages from another device:
- DM (text only)
- DM with a file / photo
- Group: post a message (you should see it)
- Group: @mention this account
- Group: reply to a previous message of this account

Press Ctrl-C to stop. Note in FINDINGS.md what fields populated for each.
"""
from __future__ import annotations

import os
import sys

from zlapi import ZaloAPI, ThreadType

from _helpers import PROBE_IMEI, load_session


class ListenerClient(ZaloAPI):
    def onMessage(
        self, mid=None, author_id=None, message=None, message_object=None,
        thread_id=None, thread_type=ThreadType.USER,
    ):
        kind = "GROUP" if thread_type == ThreadType.GROUP else "DM"
        print(f"\n[{kind}] mid={mid}  thread={thread_id}  author={author_id}")
        print(f"  text: {message!r}")
        # message_object is the rich form — dump useful attrs.
        attrs_of_interest = ("content", "msgType", "mentions", "quote", "reply",
                             "ts", "sticker", "thumb", "url", "cliMsgId")
        for a in attrs_of_interest:
            if hasattr(message_object, a):
                v = getattr(message_object, a, None)
                if v not in (None, "", []):
                    print(f"  {a}: {v!r}")

    def onListening(self):
        print(f"[listener] online as user_id={self.user_id}. Waiting for events…")


def main() -> int:
    cookies = load_session()
    if not cookies:
        print("ERR: no session.json — run probe_login.py first.", file=sys.stderr)
        return 2

    phone = os.environ.get("ZALO_PHONE", "")
    password = os.environ.get("ZALO_PASSWORD", "")
    client = ListenerClient(
        imei=PROBE_IMEI, phone=phone, password=password,
        session_cookies=cookies,
    )
    try:
        client.listen()
    except KeyboardInterrupt:
        print("\n[listener] stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

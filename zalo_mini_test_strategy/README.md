# Zalo Library Feasibility Probe

Goal: lock down what `zlapi` can / can't do **before** integrating Zalo into
the main bot codebase. Output: filled-in `FINDINGS.md`.

## Setup

```bash
# zlapi already in the main project's deps — `uv add zlapi` (already done)
# Run from project root so PYTHONPATH picks up:
uv run python zalo_mini_test_strategy/probe_login.py
```

## Order to run

1. **`probe_login.py`** — first-time login with phone + password. Saves
   session cookies to `session.json`. Run once.
2. **`probe_listen.py`** — boots a listener; prints every incoming DM /
   group message it sees. Send yourself a few messages, mention the
   account in a group, reply to its message — confirm what gets parsed.
3. **`probe_send.py`** — sends a self-DM (to your own Zalo id) plus a
   message to a chosen group. Verify they land in Zalo.
4. **`probe_group.py`** — fetches your groups + members for one group.
   Verifies `fetchAllGroups` / `fetchGroupInfo` work.
5. **`probe_rate.py`** *(optional)* — sends 5 messages back-to-back to
   feel out throttling. Stop early if Zalo flags spam.

After each probe, jot results in `FINDINGS.md`.

## Files written by probes

- `session.json` — session cookies after first login. **Do not commit.**
- `FINDINGS.md` — feasibility notes you fill in. Decides whether Phase 6b
  proceeds with `zlapi`, switches to `zca-js` subprocess, or defers Zalo.

## Safety

These scripts log into a real Zalo account. No production data is touched.
But the account is yours — be aware Zalo may flag rapid sends as spam.

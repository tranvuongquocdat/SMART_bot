# Zalo Probe Findings

Filled in as you run each probe. The end-of-doc verdict drives whether
Phase 6b ships with `zlapi`, swaps to `zca-js` subprocess, or defers Zalo.

---

## 1. Login (`probe_login.py`)

- [ ] First-time password login works
- [ ] Session cookie file `session.json` written
- [ ] Re-running with cookies skips password (no OTP/captcha)
- [ ] `client.user_id` populated correctly

**Notes / errors:**

```
(paste output here)
```

---

## 2. Listener (`probe_listen.py`)

What populates for each event type? Tick what you observed.

| Event | mid | author_id | thread_id | message (text) | message_object |
|---|---|---|---|---|---|
| DM text | [ ] | [ ] | [ ] | [ ] | [ ] |
| DM photo | [ ] | [ ] | [ ] | [ ] | [ ] |
| DM file | [ ] | [ ] | [ ] | [ ] | [ ] |
| Group text | [ ] | [ ] | [ ] | [ ] | [ ] |
| Group @mention | [ ] | [ ] | [ ] | [ ] | [ ] |
| Group reply-to | [ ] | [ ] | [ ] | [ ] | [ ] |

**`message_object` attributes that surfaced:**

```
(paste useful attrs from the printout — mentions? quote? msgType?)
```

**Did mentions / replies parse cleanly?** (Y/N + notes):

---

## 3. Send (`probe_send.py`)

- [ ] Self-DM lands
- [ ] User DM lands (different user)
- [ ] Group message lands
- [ ] Long message (1000+ chars) — does Zalo truncate?
- [ ] Markdown-style **bold** / `code` — rendered or shown raw?

**Notes:**

---

## 4. Group ops (`probe_group.py`)

- [ ] `fetchAllGroups()` returns list
- [ ] `fetchGroupInfo(id)` returns full info (name, members, admins)
- [ ] Member list includes admin flag / role

**Useful fields on the group info dict:**

```
(paste keys + sample values)
```

---

## 5. Rate limit feel (optional)

Send 5 messages back-to-back. Did Zalo throttle or flag?

- [ ] All 5 sent
- [ ] Got delayed somewhere
- [ ] Got an error / temporary block

---

## Verdict

Pick one:

- [ ] **GREEN — proceed with `zlapi`**: every critical feature works (login persistence, DM in/out, group in/out, mentions, group fetch). Rate limit acceptable.
- [ ] **YELLOW — proceed with limitations**: works for the basic flow, but [list missing features]. Defer those features in Phase 6b; document gaps in spec.
- [ ] **RED — switch to `zca-js` subprocess**: `zlapi` is too broken or stale. Plan a Node bridge.
- [ ] **DEFER — drop Zalo for now**: not enough value vs. cost given the issues found.

**Reasoning:**

```
(your call + why)
```

# Zalo Probe Findings

Probe stack: **zca-js v2.0.0-beta.27** (Node) — `zlapi` (Python) was rejected
upfront because it only supports phone+password login, which Zalo flags as bot
behaviour. zca-js mirrors what the official web client does and supports QR
login, which is the same path our reference implementation uses.

---

## 1. Login (`node_bridge/login.js`)

- [x] QR login works end-to-end
- [x] Session file `session.json` written (`cookie`, `imei`, `userAgent`)
- [x] Re-running `listen.js` with the saved session reconnects without re-scan
- [x] `api.getOwnId()` returns the bot's user_id

**Notes:**
- The `event.data.code` field returned by zca-js is a *token*, NOT the QR
  payload. Rendering it via `qrcode-terminal` produces a QR that the Zalo
  app reads as plain text and offers "Copy". The correct field is
  `event.data.image` — a base64-encoded PNG of the actual login QR. We save
  it to `qr.png` and open in the system image viewer; Zalo app scans it
  cleanly and the login flow continues.
- Event types observed (numeric):
  `0` QRCodeGenerated, `1` QRCodeExpired, `2` QRCodeScanned, `4` GotLoginInfo.
- `userAgent` is required for the saved-session reconnect — `zalo.login()`
  rejects sessions without it.

---

## 2. Listener (`node_bridge/listen.js`)

| Event | own user_id of sender | thread id | text | distinguishing fields |
|---|---|---|---|---|
| DM text | `data.uidFrom` | `threadId` (= peer uid) | `data.content` (string) | `type:0`, `cmd:501` |
| Group text | `data.uidFrom` | `threadId` (= group id) | `data.content` (string) | `type:1`, `cmd:521` |
| DM photo | `data.uidFrom` | `threadId` | `data.content` is **object** with `href`, `thumb`, `previewThumb` (base64), `title` ("[Hình ảnh]") | `msgType:"chat.photo"` |
| Group @mention | `data.uidFrom` | `threadId` | `data.content` (string with `@…`) | `data.mentions: [{uid, pos, len, type}]` |
| Group reply | `data.uidFrom` | `threadId` | `data.content` (the reply text) | `data.quote: {ownerId, msg, fromD, …}` (the message being replied to) |
| Forwarded photo / msg | same as base | same | same | `data.reference: {fwLvl, rootMsgRef, …}` present **only when forwarded** |

**Distinguishing DM vs Group:** check `type` (0 = user, 1 = group) — also matches
the `cmd` code (501 vs 521).

**Detecting "addressed to bot":**
- Group: scan `data.mentions[*].uid === own_uid`, OR `data.quote.ownerId === own_uid`.
- DM: every message is addressed to the bot.

**Forward detection:** presence of `data.reference` key. We can ignore the
content entirely if forwards are out of scope, or surface them as a separate
event.

---

## 3. Send (`node_bridge/send.js`)

- [x] Group send lands: `node send.js group <gid> "test"` → confirmed in app
- [ ] Self-DM (not exercised — `self` mode = send to own uid; Zalo may suppress
      self-chat; treat as not required for the bot use case)
- [ ] User DM (not exercised separately, but uses the same `ThreadType.User`
      path that listener inbound proves the protocol on)
- [ ] Long message / formatting — not exercised; assume Zalo's plain-text
      semantics (no Markdown), confirm during real integration if needed.

**API shape:** `await api.sendMessage({ msg: text }, threadId, ThreadType.Group | ThreadType.User)`.

---

## 4. Group ops

Not exercised in the probe — `api.fetchGroupInfo(id)` and `api.getAllGroups()`
exist on the zca-js API and are documented; deferred to real implementation.
Add a `bridge.fetch_groups` RPC method when we wire the bridge.

---

## 5. Rate limit feel

Not exercised. The reference implementation runs in production with this
library and has not reported rate limit issues for normal-cadence bot replies;
we'll add a token-bucket on the Python side as a precaution, same shape we use
for Telegram outbound.

---

## Verdict

- [x] **GREEN — proceed with `zca-js` Node bridge**

**Reasoning:**

QR login works, saved-session reconnect works, listener captures every
critical event shape (DM/Group, photo, mention, reply, forward), and outbound
send to a group lands in the app. The remaining unknowns (long messages,
formatting, rate limits, group ops) are operational detail, not feasibility
blockers — we can address them inside Phase 6b without rewriting the bridge.

**Architecture for Phase 6b:** long-running Node `bridge.js` spawned by Python
as a subprocess; JSONL RPC over stdin/stdout (commands → responses + async
events), stderr for bridge logs. Single connection per bot account. Designed
in `protocol.md` (next step).

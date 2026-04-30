# Zalo Library Feasibility Probe (zca-js bridge)

Goal: verify that `zca-js` (Node) end-to-end works for our use case
**before** building the full Python ↔ Node RPC bridge in `src/channels/zalo.py`.

The Python `zlapi` library was rejected (no QR login → relies on phone+
password which Zalo flags as bot behaviour). Reference implementation
(`reference for SMART/ZaloCRM/backend`) uses `zca-js` so we follow that.

## Layout

```
zalo_mini_test_strategy/
├── README.md           — this file
├── FINDINGS.md         — fill in as you run probes
├── node_bridge/        — pure-Node probe
│   ├── package.json    — zca-js ^2.0.0-beta.27 + qrcode-terminal
│   ├── login.js        — QR login → save session.json
│   ├── listen.js       — long-running listener, prints incoming events
│   └── send.js         — one-shot outbound send to self/user/group
└── python_client/      — (added once Node side is verified)
    └── …               — subprocess.Popen + JSON-line RPC to bridge.js
```

## Prerequisites

- Node 22+ (you have v22.20.0 already)
- `cd zalo_mini_test_strategy/node_bridge && npm install` (already done)
- A Zalo account on your phone for QR scanning

## Order

### 1. Login (run once)

```bash
cd zalo_mini_test_strategy/node_bridge
node login.js
```

Expected: a QR appears in the terminal. Open the Zalo mobile app →
Settings → "Quét mã QR" → scan it. After confirming on your phone, the
script prints `[login] OK — user_id = <id>` and writes `session.json`.

If you see the QR but scanning doesn't work, try:
- Ensure your phone's Zalo and the laptop are on the same network
- Re-run the script (the QR rotates every ~60s)

### 2. Listen

Open one terminal:

```bash
node listen.js
```

It prints `[listen] online as user_id=…`. From a second device (or your
phone), send the bot account:

- A DM with text
- A DM with a photo / file
- Post in a group it's part of
- @mention it in a group
- Reply to a previous message of it

Note in `FINDINGS.md` what fields populate. `Ctrl-C` to stop.

### 3. Send

```bash
# From listen.js output, grab a thread_id you saw.
node send.js self "test self DM"
node send.js group <group_id> "hi team"
node send.js user <user_id> "hi"
```

Verify each lands in Zalo. Note format support (Markdown? line breaks?).

### 4. Verdict in FINDINGS.md

Tick the verdict box at the bottom of `FINDINGS.md`. If green, we proceed
to write the Python client (`python_client/`) that spawns the bridge as a
subprocess and exchanges JSON-line RPC.

## Why a subprocess bridge

zca-js is a Node library. Two integration options:

1. **subprocess + stdio JSONL** — Python spawns one Node process, sends
   commands via stdin (one JSON object per line), reads responses + events
   from stdout. Single connection, simple lifecycle.
2. **HTTP/WebSocket between two services** — heavier; overkill for one
   account in a single-process bot.

We pick option 1. The bridge.js (to be written after the probes pass) will
be a long-running script that:

- Reads JSONL commands on stdin: `{"id":N,"method":"send","params":{...}}`
- Writes JSONL responses on stdout: `{"id":N,"result":{...}}`
- Writes JSONL events on stdout: `{"event":"message","data":{...}}`

Errors and bridge logs go to stderr (not interpreted by Python).

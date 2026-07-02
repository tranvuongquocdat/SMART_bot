/**
 * Fake bridge — nói ĐÚNG JSONL protocol của bridge.js (xem bridge_protocol.py),
 * không cần zca-js. Dùng cho test tầng 2 (ZaloAdapter) + tầng 3 (harness e2e).
 *
 * Env:
 *   FAKE_BRIDGE_OWN_ID  — own_id trả về (mặc định '999')
 *   FAKE_BRIDGE_OUT     — file JSONL append mọi command nhận được (test assert)
 *   FAKE_BRIDGE_CTRL    — đường dẫn unix socket điều khiển; mỗi dòng JSON:
 *                           {"inject": {<object>}}  → emit verbatim ra stdout
 *                           {"set": {"mute_replies": true, "members": [...]}}
 *
 * Giới hạn chủ đích: 1 socket path = 1 acc fake đang chạy (đủ cho test/harness).
 */

const fs = require('fs');
const net = require('net');
const readline = require('readline');

const OWN_ID = process.env.FAKE_BRIDGE_OWN_ID || '999';
const OUT = process.env.FAKE_BRIDGE_OUT || null;
const CTRL = process.env.FAKE_BRIDGE_CTRL || null;

const state = { mute_replies: false, members: ['111', '222'], sendSeq: 0 };

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function logCmd(cmd) {
  if (OUT) fs.appendFileSync(OUT, JSON.stringify(cmd) + '\n');
}

function dispatch(cmd) {
  logCmd(cmd);
  if (state.mute_replies) return;
  const { id, method } = cmd;
  if (method === 'send') {
    state.sendSeq += 1;
    emit({ id, result: { msg_id: `fake-${state.sendSeq}` } });
  } else if (method === 'fetch_members') {
    emit({ id, result: { member_ids: state.members } });
  } else if (method === 'get_own_id') {
    emit({ id, result: { own_id: OWN_ID } });
  } else if (method === 'shutdown') {
    emit({ id, result: { ok: true } });
    setTimeout(() => process.exit(0), 20);
  } else {
    emit({ id, error: { code: 'unknown_method', message: String(method) } });
  }
}

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (raw) => {
  const line = raw.trim();
  if (!line) return;
  let cmd;
  try {
    cmd = JSON.parse(line);
  } catch {
    return; // giống bridge thật: dòng rác không được phép giết process
  }
  dispatch(cmd);
});

function handleCtrlLine(line) {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }
  if (msg.inject) emit(msg.inject);
  if (msg.set) Object.assign(state, msg.set);
}

function start() {
  if (CTRL) {
    try {
      fs.unlinkSync(CTRL);
    } catch {}
    const server = net.createServer((sock) => {
      const srl = readline.createInterface({ input: sock });
      srl.on('line', handleCtrlLine);
      sock.on('error', () => {});
    });
    // 'ready' chỉ emit sau khi socket sẵn sàng — test đợi ready là inject được ngay.
    server.listen(CTRL, () => emit({ event: 'ready', data: { own_id: OWN_ID } }));
  } else {
    emit({ event: 'ready', data: { own_id: OWN_ID } });
  }
  console.error(`[fake-bridge] up own_id=${OWN_ID}`);
}

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
start();

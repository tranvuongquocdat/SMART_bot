/**
 * Long-running JSONL bridge to zca-js (single Zalo account).
 *
 * Usage: node bridge.js --session <path>
 *
 * Wire protocol:
 *   stdin:  one JSON command per line: {"id":N,"method":"send","params":{...}}
 *   stdout: one JSON object per line — either a reply ({"id":N,"result":{...}})
 *           or an event ({"event":"message","data":{...}}).
 *   stderr: free-form bridge logs (Python forwards to its logger).
 *
 * Demo scope: single account, plaintext session.json, no reconnect/circuit-
 * breaker. Phase 6b will harden this when multi-account lands.
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { Zalo, ThreadType } = require('zca-js');

let sessionPath = path.join(__dirname, 'session.json');
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--session') sessionPath = process.argv[++i];
}
if (!fs.existsSync(sessionPath)) {
  console.error(`[bridge] session not found at ${sessionPath} — run \`node login.js\` first`);
  process.exit(2);
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function logErr(stage, err, extra = {}) {
  console.error(`[bridge] ${stage}: ${err && err.stack ? err.stack : err}`,
    Object.keys(extra).length ? JSON.stringify(extra) : '');
}

function detectKind(msgType) {
  const t = String(msgType || '').toLowerCase();
  if (t.includes('photo') || t.includes('image')) return 'image';
  if (t.includes('sticker')) return 'sticker';
  if (t.includes('video')) return 'video';
  if (t.includes('voice')) return 'voice';
  if (t.includes('gif')) return 'gif';
  if (t.includes('link')) return 'link';
  if (t.includes('file') || t.includes('doc')) return 'file';
  return 'text';
}

function normalize(msg, ownId) {
  const data = msg.data || {};
  const isGroup = msg.type === 1;
  const threadId = String(msg.threadId || data.threadId || '');
  const senderUid = String(data.uidFrom || '');
  const content = data.content;

  let text = '';
  const attachments = [];
  let contentType = 'text';
  if (typeof content === 'string') {
    text = content;
  } else if (content && typeof content === 'object') {
    text = content.title || content.text || '';
    contentType = detectKind(msg.msgType);
    if (content.href) {
      attachments.push({ kind: contentType, href: content.href });
    }
  }

  const mentions = (data.mentions || []).map((m) => ({
    uid: String(m.uid || ''),
    pos: m.pos || 0,
    len: m.len || 0,
  }));
  const isMentioned = mentions.some((m) => m.uid === ownId);

  let replyTo = null;
  if (data.quote) {
    replyTo = {
      msg_id: String(data.quote.globalMsgId || data.quote.cliMsgId || ''),
      sender_uid: String(data.quote.ownerId || ''),
    };
  }

  return {
    thread_id: threadId,
    thread_type: isGroup ? 'group' : 'dm',
    sender_uid: senderUid,
    sender_name: data.dName || '',
    msg_id: String(data.msgId || data.cliMsgId || ''),
    ts_ms: Number(data.ts || 0),
    text,
    content_type: contentType,
    attachments,
    mentions,
    is_mentioned: isMentioned,
    is_forwarded: !!data.reference,
    reply_to: replyTo,
    group_name: '',
  };
}

let api = null;
let ownId = '';

async function init() {
  const session = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
  const zalo = new Zalo({ logging: false });
  api = await zalo.login({
    cookie: session.cookie,
    imei: session.imei,
    userAgent: session.userAgent,
  });
  ownId = String(await api.getOwnId());
  console.error(`[bridge] logged in as uid=${ownId}`);

  api.listener.on('message', (msg) => {
    try {
      const norm = normalize(msg, ownId);
      if (norm.sender_uid === ownId) return;
      emit({ event: 'message', data: norm });
    } catch (err) {
      logErr('normalize', err);
    }
  });
  api.listener.on('error', (err) => {
    logErr('listener', err);
    emit({ event: 'disconnected', data: { reason: String(err), fatal: false } });
  });
  api.listener.start();

  emit({ event: 'ready', data: { own_id: ownId } });
}

async function dispatch(cmd) {
  const { id, method, params } = cmd;
  try {
    if (method === 'send') {
      const tt = params.thread_type === 'group' ? ThreadType.Group : ThreadType.User;
      const result = await api.sendMessage({ msg: params.text }, params.thread_id, tt);
      const msgId = String(
        (result && (result.msgId || (result.message && result.message.msgId))) || ''
      );
      emit({ id, result: { msg_id: msgId } });
    } else if (method === 'get_own_id') {
      emit({ id, result: { own_id: ownId } });
    } else if (method === 'shutdown') {
      emit({ id, result: { ok: true } });
      setTimeout(() => process.exit(0), 50);
    } else {
      emit({ id, error: { code: 'unknown_method', message: method } });
    }
  } catch (err) {
    logErr(`dispatch:${method}`, err);
    emit({ id, error: { code: 'internal', message: String(err && err.message || err) } });
  }
}

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (raw) => {
  const line = raw.trim();
  if (!line) return;
  let cmd;
  try {
    cmd = JSON.parse(line);
  } catch (err) {
    logErr('parse-stdin', err, { line: line.slice(0, 200) });
    return;
  }
  dispatch(cmd);
});

init().catch((err) => {
  logErr('init', err);
  emit({ event: 'disconnected', data: { reason: String(err), fatal: true } });
  process.exit(1);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));

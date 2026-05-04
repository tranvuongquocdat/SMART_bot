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
const fetchModule = require('node-fetch');
const fetch = fetchModule.default || fetchModule;

const INBOUND_ROOT = path.resolve(__dirname, '..', '..', '..', 'data', 'inbound');
let cookieHeader = '';

function buildCookieHeader(session) {
  const c = session.cookie;
  if (!c) return '';
  if (typeof c === 'string') return c;
  if (Array.isArray(c)) return c.map((x) => `${x.name}=${x.value}`).join('; ');
  return '';
}

const EXT_TO_MIME = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
  gif: 'image/gif', webp: 'image/webp', heic: 'image/heic',
};

function inferMime(filename, kind) {
  const ext = (filename.split('.').pop() || '').toLowerCase();
  if (EXT_TO_MIME[ext]) return EXT_TO_MIME[ext];
  if (kind === 'image') return 'image/jpeg';
  return 'application/octet-stream';
}

function safeName(name) {
  return String(name || 'file')
    .replace(/[/\\<>:"|?*\x00-\x1f]/g, '_')
    .slice(0, 100);
}

async function downloadAttachment(href, threadId, msgId, filename) {
  const dir = path.join(INBOUND_ROOT, String(threadId));
  fs.mkdirSync(dir, { recursive: true });
  const local = path.join(dir, `${msgId}_${safeName(filename)}`);
  const headers = { 'User-Agent': 'Mozilla/5.0' };
  if (cookieHeader) headers['Cookie'] = cookieHeader;
  // Hard 15s timeout — Zalo CDN occasionally hangs; without this the
  // listener handler stalls forever and new messages stop processing.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  let resp;
  try {
    resp = await fetch(href, { headers, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const buf = Buffer.from(await resp.arrayBuffer());
  fs.writeFileSync(local, buf);
  console.error(`[bridge] downloaded ${filename} -> ${local} (${buf.length}B)`);
  return { local_path: local, size_bytes: buf.length };
}

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

async function normalize(msg, ownId) {
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
      const params = content.params || {};
      const fileName = params.fileName || content.title || 'file';
      const mime = inferMime(fileName, contentType);
      const att = { kind: contentType, mime, filename: fileName };
      try {
        const dl = await downloadAttachment(
          content.href,
          threadId,
          String(data.msgId || data.cliMsgId || Date.now()),
          fileName,
        );
        att.local_path = dl.local_path;
        att.size_bytes = Number(params.totalSize || dl.size_bytes || 0);
      } catch (err) {
        att.error = String((err && err.message) || err);
        logErr('download', err, { href: content.href, fileName });
      }
      attachments.push(att);
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
  cookieHeader = buildCookieHeader(session);
  const zalo = new Zalo({ logging: false });
  api = await zalo.login({
    cookie: session.cookie,
    imei: session.imei,
    userAgent: session.userAgent,
  });
  ownId = String(await api.getOwnId());
  console.error(`[bridge] logged in as uid=${ownId}`);

  api.listener.on('message', async (msg) => {
    // Diagnostic: surface every incoming event so we can tell if zca-js
    // is even firing for the message in question (especially file/photo).
    try {
      const summary = {
        type: msg && msg.type,
        msgType: msg && msg.msgType,
        threadId: msg && (msg.threadId || (msg.data && msg.data.threadId)),
        contentKind: typeof (msg && msg.data && msg.data.content),
        hasHref: !!(msg && msg.data && msg.data.content && msg.data.content.href),
      };
      console.error('[bridge] msg event:', JSON.stringify(summary));
    } catch (_) {}
    try {
      const norm = await normalize(msg, ownId);
      console.error('[bridge] post-normalize:', JSON.stringify({
        sender_uid: norm.sender_uid,
        ownId: ownId,
        is_self: norm.sender_uid === ownId,
        text_len: (norm.text || '').length,
        n_attachments: (norm.attachments || []).length,
        first_att: (norm.attachments || [])[0] || null,
      }));
      if (norm.sender_uid === ownId) return;
      emit({ event: 'message', data: norm });
      console.error('[bridge] emitted message');
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

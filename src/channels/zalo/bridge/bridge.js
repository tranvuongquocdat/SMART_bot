/**
 * Long-running JSONL bridge to zca-js (single Zalo bot_account).
 *
 * Usage: node bridge.js [--session <path>]
 *   default session path = $SESSION_PATH (env) || ./session.json
 *
 * Wire protocol (see ../bridge_protocol.py):
 *   stdin  — one JSON command per line: {"id":N,"method":...,"params":{...}}
 *   stdout — one JSON object per line:
 *              reply: {"id":N,"result":{...}} | {"id":N,"error":{...}}
 *              event: {"event":"message"|"ready"|"disconnected"|"status","data":{...}}
 *   stderr — free-form bridge logs (Python forwards to its logger).
 *
 * Adapted from spike `spikes/zalo-2026/bridge.js` for zca-js v2.1.x.
 * Key API changes from v2.0-beta:
 *   - api.listener.on('message', cb)  →  api.listener.onMessage(cb)
 *   - api.fetchGroupInfo(gid)         →  api.getGroupInfo([gid])
 *                                          .gridInfoMap[gid].memVerList
 *                                          memVerList[i] = "<userId>_<version>"
 *   - new Zalo({selfListen: true})    — optional, needed to echo own messages
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { Zalo, ThreadType } = require('zca-js');

let sessionPath =
  process.env.SESSION_PATH || path.join(__dirname, 'session.json');
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--session') sessionPath = process.argv[++i];
}

if (!fs.existsSync(sessionPath)) {
  console.error(
    `[bridge] session not found at ${sessionPath} — run login.js to provision`,
  );
  process.exit(2);
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function logErr(stage, err, extra = {}) {
  console.error(
    `[bridge] ${stage}: ${err && err.stack ? err.stack : err}`,
    Object.keys(extra).length ? JSON.stringify(extra) : '',
  );
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
  let mediaUrl = null;
  let contentType = 'text';
  if (typeof content === 'string') {
    text = content;
  } else if (content && typeof content === 'object') {
    text = content.title || content.text || '';
    contentType = detectKind(msg.msgType);
    if (content.href) mediaUrl = String(content.href);
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
    type: msg.type, // 0 = dm, 1 = group (kept for normalizer.py)
    threadId,
    thread_id: threadId,
    thread_type: isGroup ? 'group' : 'dm',
    uidFrom: senderUid,
    sender_uid: senderUid,
    dName: String(data.dName || ''),
    sender_name: String(data.dName || ''),
    msg_id: String(data.msgId || data.cliMsgId || ''),
    msgId: String(data.msgId || data.cliMsgId || ''),
    ts: Number(data.ts || 0),
    ts_ms: Number(data.ts || 0),
    text,
    content: text,
    content_type: contentType,
    media_url: mediaUrl,
    mentions,
    is_mentioned: isMentioned,
    is_forwarded: !!data.reference,
    reply_to: replyTo,
  };
}

let api = null;
let ownId = '';

function zaloOptions() {
  // PROXY_URL được Python (adapter) gán theo proxy của boss sở hữu acc.
  // zca-js qua proxy cần http.Agent + polyfill node-fetch (undici global fetch
  // không dùng http.Agent).
  const opts = { logging: false, selfListen: false };
  const proxyUrl = process.env.PROXY_URL;
  if (proxyUrl) {
    const { ProxyAgent } = require('proxy-agent');
    opts.agent = new ProxyAgent(proxyUrl);
    opts.polyfill = require('node-fetch');
    console.error('[bridge] using proxy');
  }
  return opts;
}

async function init() {
  const session = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
  const zalo = new Zalo(zaloOptions());
  api = await zalo.login({
    cookie: session.cookie,
    imei: session.imei,
    userAgent: session.userAgent,
  });
  ownId = String(await api.getOwnId());
  console.error(`[bridge] logged in as uid=${ownId}`);

  // v2.1: api.listener.onMessage(cb), not api.listener.on('message',...)
  api.listener.onMessage(async (msg) => {
    try {
      const norm = normalize(msg, ownId);
      if (norm.sender_uid === ownId) return; // skip self
      emit({ event: 'message', data: norm, own_uid: ownId });
    } catch (err) {
      logErr('normalize', err);
    }
  });

  // Most v2.x listeners expose onError; fall back to .on('error',...) if needed.
  if (typeof api.listener.onError === 'function') {
    api.listener.onError((err) => {
      logErr('listener', err);
      emit({
        event: 'disconnected',
        data: { reason: String(err), fatal: false },
      });
    });
  }

  api.listener.start();
  emit({ event: 'ready', data: { own_id: ownId } });
}

async function fetchMembers(groupId) {
  // v2.1: api.getGroupInfo([gid]) → {gridInfoMap}; memVerList[i] = "<uid>_<v>"
  const info = await api.getGroupInfo([groupId]);
  const gi = info && info.gridInfoMap && info.gridInfoMap[groupId];
  if (!gi) return [];
  const memVer = Array.isArray(gi.memVerList) ? gi.memVerList : [];
  return memVer.map((s) => String(s).split('_', 1)[0]);
}

async function dispatch(cmd) {
  const { id, method, params } = cmd;
  try {
    if (method === 'send') {
      const tt =
        params.thread_kind === 'group' ? ThreadType.Group : ThreadType.User;
      const target = params.thread_id || params.chat_id;
      const result = await api.sendMessage(
        { msg: params.text },
        target,
        tt,
      );
      const msgId = String(
        (result && (result.msgId || (result.message && result.message.msgId))) ||
          '',
      );
      emit({ id, result: { msg_id: msgId } });
    } else if (method === 'fetch_members') {
      const gid = params.group_id;
      const ids = await fetchMembers(gid);
      emit({ id, result: { member_ids: ids } });
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
    emit({
      id,
      error: {
        code: 'internal',
        message: String((err && err.message) || err),
      },
    });
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
  emit({
    event: 'disconnected',
    data: { reason: String(err), fatal: true },
  });
  process.exit(1);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));

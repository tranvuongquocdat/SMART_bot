/**
 * Minimal listener probe — print inbound message events as JSONL for 90s.
 *   node probe_listener.js
 */
const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const zalo = new Zalo({ logging: false, selfListen: true });
  const api = await zalo.login(session);
  const ownId = await api.getOwnId();
  console.error(`OK login. own_id=${ownId}. selfListen=true. listening 90s...`);

  // Try setter-style callbacks (v2.1.2 idiomatic)
  api.listener.onMessage((msg) => {
    try {
      const ev = {
        kind: 'message',
        type: msg.type,
        threadId: msg.threadId,
        uidFrom: msg.data?.uidFrom,
        isSelf: String(msg.data?.uidFrom) === String(ownId),
        content_type: typeof msg.data?.content,
        content_preview: typeof msg.data?.content === 'string'
          ? msg.data.content.slice(0, 100)
          : (msg.data?.content?.title || JSON.stringify(msg.data?.content).slice(0, 200)),
        mentions: msg.data?.mentions || [],
        mentions_self: (msg.data?.mentions || []).some(m => String(m.uid) === String(ownId)),
        msgType: msg.data?.msgType,
        cmd: msg.data?.cmd,
        has_quote: !!msg.data?.quote,
        has_reference: !!msg.data?.reference,
      };
      console.log(JSON.stringify(ev));
    } catch (e) {
      console.error('handler err:', e.message);
    }
  });
  api.listener.onConnected(() => console.error('[listener] CONNECTED'));
  api.listener.onError((e) => console.error('[listener] ERROR', e && e.message));
  api.listener.onClosed((c) => console.error('[listener] CLOSED', c));

  api.listener.start();
  setTimeout(() => { console.error('listener done'); process.exit(0); }, 90_000);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

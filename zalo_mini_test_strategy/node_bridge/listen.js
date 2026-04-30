/**
 * Probe 2 — listener. Reuses session.json from login.js.
 *
 * Run: `npm run listen` (or `node listen.js`).
 *
 * What it does:
 *   - Reconnects with saved session
 *   - Attaches event listeners (message, group_event, etc.)
 *   - Pretty-prints every event to stdout
 *
 * From your other Zalo device, send the bot account:
 *   - DM text
 *   - DM photo / file
 *   - Post in a group it's part of
 *   - @mention it in a group
 *   - Reply to one of its messages
 *
 * Ctrl-C to stop. Note in FINDINGS.md what fields are useful.
 */

const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');

function summarizeMessage(msg) {
  // The zca-js Message object has a flat shape we can mostly JSON.stringify.
  // Trim the body to keep stdout readable.
  try {
    const j = JSON.parse(JSON.stringify(msg));
    return j;
  } catch {
    return String(msg);
  }
}

async function main() {
  if (!fs.existsSync(SESSION_PATH)) {
    console.error(`[listen] missing ${SESSION_PATH} — run login.js first.`);
    process.exit(2);
  }
  const session = JSON.parse(fs.readFileSync(SESSION_PATH, 'utf8'));

  const zalo = new Zalo({ logging: false });
  const api = await zalo.login({
    cookie: session.cookie,
    imei: session.imei,
    userAgent: session.userAgent,
  });

  const ownId = await api.getOwnId();
  console.log(`[listen] online as user_id=${ownId}. Waiting for events…\n`);

  // Subscribe to common events. zca-js exposes `api.listener` or similar —
  // event names differ slightly across versions; this set covers v2.x.
  const listener = api.listener;

  if (!listener) {
    console.error('[listen] api.listener not available — version mismatch?');
    console.error('[listen] api keys:', Object.keys(api).slice(0, 30));
    process.exit(3);
  }

  listener.on('message', (msg) => {
    console.log('\n[event:message]');
    console.log(JSON.stringify(summarizeMessage(msg), null, 2).slice(0, 1500));
  });

  listener.on('group_event', (ev) => {
    console.log('\n[event:group_event]');
    console.log(JSON.stringify(ev, null, 2).slice(0, 1000));
  });

  listener.on('reaction', (r) => {
    console.log('[event:reaction]', JSON.stringify(r).slice(0, 300));
  });

  listener.on('undo', (u) => {
    console.log('[event:undo]', JSON.stringify(u).slice(0, 300));
  });

  listener.on('error', (err) => {
    console.error('[event:error]', err);
  });

  listener.start();

  process.on('SIGINT', () => {
    console.log('\n[listen] stopping…');
    process.exit(0);
  });
}

main().catch((err) => {
  console.error('[listen] ERR:', err);
  process.exit(1);
});

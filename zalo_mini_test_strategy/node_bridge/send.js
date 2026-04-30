/**
 * Probe 3 — outbound send.
 *
 * Run:
 *   node send.js self "hello to myself"
 *   node send.js user 1234567890 "hi"
 *   node send.js group 9876543210 "hi team"
 *
 * Get user/group IDs from listen.js output (`thread_id` / `groupId` fields).
 */

const fs = require('fs');
const path = require('path');
const { Zalo, ThreadType } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');

async function main() {
  const [kind, threadId, ...textParts] = process.argv.slice(2);
  const text = textParts.join(' ');

  if (!kind || (kind !== 'self' && (!threadId || !text))) {
    console.error('Usage: node send.js self "<text>"');
    console.error('       node send.js user <user_id> "<text>"');
    console.error('       node send.js group <group_id> "<text>"');
    process.exit(2);
  }

  if (!fs.existsSync(SESSION_PATH)) {
    console.error(`[send] missing ${SESSION_PATH} — run login.js first.`);
    process.exit(2);
  }
  const session = JSON.parse(fs.readFileSync(SESSION_PATH, 'utf8'));

  const zalo = new Zalo({ logging: false });
  const api = await zalo.login({
    cookie: session.cookie,
    imei: session.imei,
    userAgent: session.userAgent,
  });

  let target;
  let threadType;
  if (kind === 'self') {
    target = await api.getOwnId();
    threadType = ThreadType.User;
    console.log(`[send] → self (${target}): ${JSON.stringify(text)}`);
  } else if (kind === 'user') {
    target = threadId;
    threadType = ThreadType.User;
    console.log(`[send] → user ${target}: ${JSON.stringify(text)}`);
  } else if (kind === 'group') {
    target = threadId;
    threadType = ThreadType.Group;
    console.log(`[send] → group ${target}: ${JSON.stringify(text)}`);
  } else {
    console.error(`[send] unknown kind: ${kind}`);
    process.exit(2);
  }

  const result = await api.sendMessage({ msg: text }, target, threadType);
  console.log('[send] result:', JSON.stringify(result, null, 2).slice(0, 600));
  process.exit(0);
}

main().catch((err) => {
  console.error('[send] ERR:', err);
  process.exit(1);
});

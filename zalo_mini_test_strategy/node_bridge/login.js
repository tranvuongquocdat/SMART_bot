/**
 * Probe 1 — QR login.
 *
 * Run: `npm run login` (or `node login.js`).
 *
 * What it does:
 *   - Calls zca-js loginQR
 *   - Renders the QR image in the terminal (qrcode-terminal)
 *   - Waits for the user to scan with the Zalo mobile app
 *   - On success, saves { cookie, imei, userAgent } to ./session.json
 *   - Prints user_id and exits
 *
 * After this works once, future runs (listen.js, send.js) reuse the saved session.
 */

const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode-terminal');
const { Zalo } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');

async function main() {
  if (fs.existsSync(SESSION_PATH)) {
    console.log(`[login] session.json already exists at ${SESSION_PATH}.`);
    console.log('[login] Delete it first if you want to redo QR login.');
    process.exit(0);
  }

  const zalo = new Zalo({ logging: false });
  console.log('[login] starting QR login… open Zalo on your phone → Settings → QR scanner');

  let qrShown = false;
  const api = await zalo.loginQR({}, (event) => {
    switch (event.type) {
      case 0: // QRCodeGenerated
        if (!qrShown) {
          console.log('\n[login] scan this QR with the Zalo mobile app:\n');
          // event.data.image is base64 data URL — but the zca-js QR data is
          // the underlying URL string we can render directly.
          // Fallback: print the raw URL too so you can paste into a QR-decoder
          // app if the terminal renderer fails.
          if (event.data.code) {
            QRCode.generate(event.data.code, { small: true });
            console.log(`\n[login] (raw QR string: ${event.data.code})\n`);
          } else {
            console.log('[login] event.data:', JSON.stringify(event.data).slice(0, 400));
          }
          qrShown = true;
        }
        break;
      case 1: // QRCodeExpired
        console.log('[login] QR expired — retrying…');
        if (event.actions?.retry) event.actions.retry();
        qrShown = false;
        break;
      case 2: // QRCodeScanned
        console.log(`[login] scanned by ${event.data.display_name || '?'} — confirm on phone…`);
        break;
      case 4: // GotLoginInfo
        console.log('[login] login info received, saving session…');
        const session = {
          cookie: event.data.cookie,
          imei: event.data.imei,
          userAgent: event.data.userAgent,
        };
        fs.writeFileSync(SESSION_PATH, JSON.stringify(session, null, 2));
        console.log(`[login] session saved → ${SESSION_PATH}`);
        break;
      default:
        console.log(`[login] event type=${event.type}`);
    }
  });

  const ownId = await api.getOwnId();
  console.log(`[login] OK — user_id = ${ownId}`);
  process.exit(0);
}

main().catch((err) => {
  console.error('[login] ERR:', err);
  process.exit(1);
});

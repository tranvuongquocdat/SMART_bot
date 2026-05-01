/**
 * Zalo QR login — produces session.json next to this file.
 *
 *   node login.js [--force]
 *
 * Opens the QR image in the system viewer; scan with the Zalo app
 * (Settings → Quét mã QR). Re-run with --force to redo a logged-in account.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { Zalo } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');
const QR_PATH = path.join(__dirname, 'qr.png');

const force = process.argv.includes('--force');

if (fs.existsSync(SESSION_PATH) && !force) {
  console.log(`session.json already exists at ${SESSION_PATH}`);
  console.log('pass --force to overwrite.');
  process.exit(0);
}

function openImage(p) {
  for (const cmd of [`open ${JSON.stringify(p)}`, `xdg-open ${JSON.stringify(p)}`]) {
    try { execSync(cmd); return; } catch {}
  }
  console.log(`open ${p} manually to scan`);
}

(async () => {
  const zalo = new Zalo({ logging: false });
  console.log('starting QR login… open Zalo on your phone → Settings → Quét mã QR');

  let opened = false;
  const api = await zalo.loginQR({}, (event) => {
    switch (event.type) {
      case 0: { // QRCodeGenerated
        const b64 = (event.data.image || '').replace(/^data:image\/\w+;base64,/, '');
        if (!b64) return;
        fs.writeFileSync(QR_PATH, Buffer.from(b64, 'base64'));
        if (!opened) { console.log(`QR → ${QR_PATH}`); openImage(QR_PATH); opened = true; }
        else console.log('QR refreshed');
        break;
      }
      case 1: console.log('QR expired, retrying…'); event.actions?.retry?.(); opened = false; break;
      case 2: console.log(`scanned by ${event.data.display_name || '?'} — confirm on phone`); break;
      case 4: {
        const session = {
          cookie: event.data.cookie,
          imei: event.data.imei,
          userAgent: event.data.userAgent,
        };
        fs.writeFileSync(SESSION_PATH, JSON.stringify(session, null, 2));
        console.log(`session saved → ${SESSION_PATH}`);
        break;
      }
    }
  });
  const ownId = await api.getOwnId();
  console.log(`OK — user_id = ${ownId}`);
  process.exit(0);
})().catch((err) => { console.error('ERR:', err); process.exit(1); });

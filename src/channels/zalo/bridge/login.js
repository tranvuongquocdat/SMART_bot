/**
 * Zalo QR login — provisions a session blob (cookie + imei + userAgent) that
 * Python encrypts before storing in ``bot_accounts.credentials_blob_enc``.
 *
 *   node login.js [--out <path>] [--force]
 *
 * Opens the QR image in the system viewer; scan with the Zalo app
 * (Settings → Quét mã QR). Output JSON contains exactly the fields the
 * bridge needs to re-init: { cookie, imei, userAgent }.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { Zalo } = require('zca-js');

let outPath = path.join(__dirname, 'session.json');
let force = false;
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--out') outPath = process.argv[++i];
  else if (process.argv[i] === '--force') force = true;
}

const QR_PATH = path.join(path.dirname(outPath), 'qr.png');

if (fs.existsSync(outPath) && !force) {
  console.log(`session already exists at ${outPath} — pass --force to overwrite`);
  process.exit(0);
}

function openImage(p) {
  for (const cmd of [
    `open ${JSON.stringify(p)}`,
    `xdg-open ${JSON.stringify(p)}`,
  ]) {
    try {
      execSync(cmd);
      return;
    } catch {}
  }
  console.log(`open ${p} manually to scan`);
}

(async () => {
  const zalo = new Zalo({ logging: false });
  console.log('starting QR login… open Zalo on your phone → Settings → Quét mã QR');

  let opened = false;
  const api = await zalo.loginQR({}, (event) => {
    switch (event.type) {
      case 0: {
        const b64 = (event.data.image || '').replace(/^data:image\/\w+;base64,/, '');
        if (!b64) return;
        fs.writeFileSync(QR_PATH, Buffer.from(b64, 'base64'));
        if (!opened) {
          console.log(`QR → ${QR_PATH}`);
          openImage(QR_PATH);
          opened = true;
        } else console.log('QR refreshed');
        break;
      }
      case 1:
        console.log('QR expired, retrying…');
        event.actions?.retry?.();
        opened = false;
        break;
      case 2:
        console.log(`scanned by ${event.data.display_name || '?'} — confirm on phone`);
        break;
      case 4: {
        const session = {
          cookie: event.data.cookie,
          imei: event.data.imei,
          userAgent: event.data.userAgent,
        };
        fs.writeFileSync(outPath, JSON.stringify(session, null, 2));
        console.log(`session saved → ${outPath}`);
        break;
      }
    }
  });
  const ownId = await api.getOwnId();
  console.log(`OK — user_id = ${ownId}`);
  process.exit(0);
})().catch((err) => {
  console.error('ERR:', err);
  process.exit(1);
});

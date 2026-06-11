/**
 * Zalo QR login — headless, dùng cho luồng boss tự kết nối acc phụ từ web.
 *
 * Khác login.js (CLI mở ảnh QR cho dev): script này emit NDJSON ra stdout để
 * Python stream QR về trình duyệt và nhận session khi user quét xong:
 *
 *   {"event":"qr","data":{"image":"<base64 png>"}}
 *   {"event":"scanned","data":{"display_name":"..."}}
 *   {"event":"success","data":{"cookie":...,"imei":"...","userAgent":"...","own_id":"...","display_name":"..."}}
 *   {"event":"error","data":{"message":"..."}}
 *
 * Tự thoát sau success/error hoặc LOGIN_TIMEOUT_MS (mặc định 180s).
 */

const { Zalo } = require('zca-js');

const TIMEOUT_MS = parseInt(process.env.LOGIN_TIMEOUT_MS || '180000', 10);

function emit(event, data) {
  process.stdout.write(JSON.stringify({ event, data }) + '\n');
}

const killer = setTimeout(() => {
  emit('error', { message: 'QR login timeout' });
  process.exit(1);
}, TIMEOUT_MS);

(async () => {
  const zalo = new Zalo({ logging: false });
  let scannedName = null;

  const api = await zalo.loginQR({}, (event) => {
    switch (event.type) {
      case 0: {
        const b64 = (event.data.image || '').replace(/^data:image\/\w+;base64,/, '');
        if (b64) emit('qr', { image: b64 });
        break;
      }
      case 1:
        event.actions?.retry?.();
        break;
      case 2:
        scannedName = event.data.display_name || null;
        emit('scanned', { display_name: scannedName });
        break;
      case 4:
        // Session sẵn sàng — own_id lấy sau khi loginQR resolve.
        global.__session = {
          cookie: event.data.cookie,
          imei: event.data.imei,
          userAgent: event.data.userAgent,
        };
        break;
    }
  });

  const ownId = await api.getOwnId();
  clearTimeout(killer);
  emit('success', {
    ...(global.__session || {}),
    own_id: String(ownId),
    display_name: scannedName,
  });
  process.exit(0);
})().catch((err) => {
  clearTimeout(killer);
  emit('error', { message: String(err && err.message ? err.message : err) });
  process.exit(1);
});

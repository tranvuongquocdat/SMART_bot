const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');
(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const api = await new Zalo({ logging: false }).login(session);
  const L = api.listener;
  console.log('typeof api.listener:', typeof L);
  console.log('listener constructor:', L && L.constructor && L.constructor.name);
  console.log('listener own keys:', Object.getOwnPropertyNames(L));
  let proto = Object.getPrototypeOf(L);
  console.log('listener proto:', proto && proto.constructor && proto.constructor.name);
  console.log('listener proto methods:', Object.getOwnPropertyNames(proto || {}));
  let proto2 = Object.getPrototypeOf(proto || {});
  if (proto2) console.log('listener proto^2 methods:', Object.getOwnPropertyNames(proto2));
  process.exit(0);
})();

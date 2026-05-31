const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const zalo = new Zalo({ logging: false });
  const api = await zalo.login(session);

  console.log('=== api methods (own + prototype) ===');
  const allKeys = new Set();
  let proto = api;
  while (proto && proto !== Object.prototype) {
    Object.getOwnPropertyNames(proto).forEach(k => allKeys.add(k));
    proto = Object.getPrototypeOf(proto);
  }
  const methods = [...allKeys]
    .filter(k => typeof api[k] === 'function' && k !== 'constructor')
    .sort();
  console.log('total methods:', methods.length);
  methods.forEach(m => console.log(' -', m));

  // also list grouped by likely-purpose
  console.log('\n=== group-related methods ===');
  methods.filter(m => /group/i.test(m)).forEach(m => console.log(' *', m));
  console.log('\n=== member-related methods ===');
  methods.filter(m => /member/i.test(m)).forEach(m => console.log(' *', m));
  console.log('\n=== getAll* methods ===');
  methods.filter(m => /^getAll/i.test(m)).forEach(m => console.log(' *', m));
  console.log('\n=== fetch* methods ===');
  methods.filter(m => /^fetch/i.test(m)).forEach(m => console.log(' *', m));

  process.exit(0);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

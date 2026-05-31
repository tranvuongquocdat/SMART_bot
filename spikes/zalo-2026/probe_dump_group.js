const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');
(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const api = await new Zalo({ logging: false }).login(session);
  const groups = await api.getAllGroups();
  const gids = Object.keys(groups.gridVerMap || {});
  // pick group with most members from gridVerMap (need to fetch info for sample of 10)
  let best = null; let bestN = 0;
  for (let i = 0; i < Math.min(10, gids.length); i++) {
    const info = await api.getGroupInfo([gids[i]]);
    const g = info.gridInfoMap[gids[i]];
    if (g && g.totalMember > bestN) { bestN = g.totalMember; best = gids[i]; }
    await new Promise(r => setTimeout(r, 200));
  }
  console.log(`picked gid=${best} totalMember=${bestN}\n`);
  const info = await api.getGroupInfo([best]);
  const g = info.gridInfoMap[best];
  console.log('=== ALL FIELDS ===');
  for (const [k, v] of Object.entries(g)) {
    const desc = Array.isArray(v) ? `array(${v.length})${v.length<=5?' '+JSON.stringify(v).slice(0,200):''}`
               : typeof v === 'object' && v ? `object{${Object.keys(v).slice(0,8).join(',')}}`
               : JSON.stringify(v)?.slice(0, 200);
    console.log(`  ${k}: ${desc}`);
  }
  process.exit(0);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

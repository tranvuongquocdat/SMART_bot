const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const zalo = new Zalo({ logging: false });
  const api = await zalo.login(session);
  const ownId = await api.getOwnId();

  const groups = await api.getAllGroups();
  const gids = Object.keys(groups.gridVerMap || {});

  console.log(`probing ${Math.min(5, gids.length)} groups...\n`);
  for (let i = 0; i < Math.min(5, gids.length); i++) {
    const gid = gids[i];
    try {
      const info = await api.getGroupInfo([gid]);
      const g = info.gridInfoMap[gid];
      if (!g) { console.log(`[${i}] ${gid}: <not in gridInfoMap>`); continue; }
      const memberCount = (g.memberIds || []).length;
      console.log(`[${i}] gid=${gid} name="${(g.name||'').slice(0,40)}" totalMember=${g.totalMember} memberIds.len=${memberCount} hasMoreMember=${g.hasMoreMember} adminIds.len=${(g.adminIds||[]).length}`);
      if (memberCount > 0) {
        console.log(`     own_in_memberIds=${g.memberIds.includes(ownId)} sample_member=${g.memberIds.slice(0, 2)}`);
        // Try resolving member profiles
        try {
          const mem = await api.getGroupMembersInfo(gid, g.memberIds.slice(0, 3));
          console.log(`     getGroupMembersInfo(gid, [3 ids]) profiles.len=${Object.keys(mem.profiles || {}).length}`);
        } catch (e) {
          console.log(`     getGroupMembersInfo FAIL: ${e.message}`);
        }
      }
    } catch (e) {
      console.log(`[${i}] ${gid}: ERR ${e.message}`);
    }
    await new Promise(r => setTimeout(r, 500));  // small spacing, avoid burst
  }
  process.exit(0);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

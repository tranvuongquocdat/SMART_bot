/**
 * Probe group operations — zca-js v2.1.2 API.
 *   node probe_group_ops.js
 */
const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const zalo = new Zalo({ logging: false });
  const api = await zalo.login(session);
  const ownId = await api.getOwnId();
  console.log(`OK login. own_id=${ownId}`);

  console.log('\n=== getAllGroups ===');
  const groups = await api.getAllGroups();
  console.log('top-level keys:', Object.keys(groups));
  console.log('version:', groups.version);
  const gridMap = groups.gridVerMap || {};
  const gids = Object.keys(gridMap);
  console.log(`group count: ${gids.length}`);
  console.log('first 3 gids:', gids.slice(0, 3));

  if (!gids.length) { console.log('no groups — done'); process.exit(0); }
  const gid = gids[0];

  console.log(`\n=== getGroupInfo([${gid}]) ===`);
  let info;
  try {
    info = await api.getGroupInfo([gid]);  // v2 expects array
  } catch (e) {
    console.error('getGroupInfo FAIL (array form):', e.message);
    try { info = await api.getGroupInfo(gid); console.log('  → works with string arg'); }
    catch (e2) { console.error('getGroupInfo FAIL (string form):', e2.message); }
  }
  if (info) {
    console.log('top-level keys:', Object.keys(info).slice(0, 20));
    const map = info.gridInfoMap || info;
    const grp = map[gid] || info;
    console.log('group keys:', Object.keys(grp).slice(0, 30));
    console.log('group name:', grp.name || grp.groupName);
    console.log('member count (from group obj):', (grp.memberIDs || grp.members || []).length);
    console.log('owner:', grp.creatorId || grp.adminId || '<n/a>');
  }

  console.log(`\n=== getGroupMembersInfo(${gid}) ===`);
  try {
    const mem = await api.getGroupMembersInfo(gid);
    console.log('return type:', typeof mem);
    console.log('top-level keys:', Object.keys(mem || {}).slice(0, 15));
    const list = mem.members || mem.profiles || mem;
    if (Array.isArray(list)) {
      console.log(`member count: ${list.length}`);
      if (list[0]) console.log('member sample keys:', Object.keys(list[0]).slice(0, 15));
      console.log('own in members?', list.some(m => (m.userId || m.uid || m.id) == ownId));
    } else {
      console.log('not array — dump first 1500 chars:');
      console.log(JSON.stringify(mem, null, 2).slice(0, 1500));
    }
  } catch (e) {
    console.error('getGroupMembersInfo FAIL:', e.message);
  }

  process.exit(0);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

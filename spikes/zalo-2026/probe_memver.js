const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');
(async () => {
  const session = JSON.parse(fs.readFileSync(path.join(__dirname, 'session.json')));
  const api = await new Zalo({ logging: false }).login(session);
  const gid = '8379600892570492340';
  const info = await api.getGroupInfo([gid]);
  const g = info.gridInfoMap[gid];
  console.log('memVerList sample [0:5]:');
  console.log(JSON.stringify(g.memVerList.slice(0, 5), null, 2));
  console.log('\n--- check element shape ---');
  console.log('type of [0]:', typeof g.memVerList[0]);
  console.log('Object.keys([0]):', typeof g.memVerList[0] === 'object' ? Object.keys(g.memVerList[0]).slice(0,10) : '(not object)');

  // Try getGroupMembersInfo with array of IDs (extract from memVerList)
  const memberIdsCandidate = g.memVerList.slice(0, 5).map(m =>
    typeof m === 'string' ? m : (m.id || m.userId || m.uid || JSON.stringify(m).slice(0,30))
  );
  console.log('candidate member IDs:', memberIdsCandidate);

  console.log('\n=== Try getGroupMembersInfo with array ===');
  try {
    const res = await api.getGroupMembersInfo(gid, memberIdsCandidate);
    console.log('top-level keys:', Object.keys(res || {}));
    if (res.profiles) {
      const ids = Object.keys(res.profiles);
      console.log('profile count:', ids.length);
      console.log('first profile sample:', JSON.stringify(res.profiles[ids[0]], null, 2).slice(0,500));
    }
  } catch (e) {
    console.log('FAIL:', e.message);
  }
  process.exit(0);
})().catch(e => { console.error('ERR:', e.message); process.exit(1); });

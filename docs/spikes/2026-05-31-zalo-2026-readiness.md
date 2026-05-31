# Zalo 2026 Readiness — Spike 2026-05-31

**Library tested:** `zca-js@2.1.2` (Node 24.11.1)
**Reference probe v1:** `docs/legacy/zalo-probe-findings.md` (Q4 2025, zca-js v2.0.0-beta.27)
**Test account:** Trần Đạt K (anh's test acc); own_id = 2217794087799994937
**Workspace:** `spikes/zalo-2026/`

## Conclusion: **GO**

zca-js v2.1.2 hoạt động ổn cho MVP scope. Có **API rename** vs probe v1 (xem §API matrix). Cập nhật spec §10.1 (đã từng ghi `zlapi-py` sai) → `zca-js Node bridge`.

## API matrix

| Capability | Status | Note |
|---|---|---|
| QR login + session save | **PASS** | `qr.png` mở qua xdg-open (eog warn về display là expected — anh scan OK trên app); session.json gồm {cookie, imei, userAgent} match probe v1 |
| Saved session reconnect | **PASS** | `new Zalo(...).login(session)` re-init không scan; chạy lại nhiều lần (probe_group_ops, probe_listener) đều OK |
| `getAllGroups()` | **PASS — shape ĐỔI** | Trả `{version, gridVerMap}`; `gridVerMap` = `{gid: version}` map, KHÔNG phải `gridInfoMap` |
| `getGroupInfo([gid])` | **PASS — replaces `fetchGroupInfo`** | `fetchGroupInfo` không tồn tại trong v2.1.2. Phải truyền **array** `[gid]`. Trả `{removedsGroup, unchangedsGroup, gridInfoMap}` |
| Group info fields | **PASS** | `gridInfoMap[gid]` có: `groupId, name, desc, type, creatorId, version, memberIds, adminIds, currentMems, updateMems, memVerList, hasMoreMember, totalMember, maxMember, setting, createdTime` |
| Member ID resolution | **PASS** | `memberIds` empty trong response (đặc trưng delta sync), **dùng `memVerList`**: array of `"<userId>_<version>"` strings; split `_` → userId. `memVerList.length == totalMember`. Confirmed group `8379600892570492340` (746 members) match. |
| `getGroupMembersInfo(gid, [ids])` | **PARTIAL** | Trả `{profiles, unchangeds_profile}` nhưng chỉ 1 profile/call, shape lạ (id field = gid không phải member id). KHÔNG cần cho MVP — `memVerList` đủ resolve, sender display name lấy từ inbound event. |
| Listener connect | **PASS** | `api.listener.onConnected(cb)` fires; WS hookup OK |
| Listener message capture | **NOT EXERCISED** (skipped) | Anh chưa gửi test message — defer verify sang Task E1 implementation. Listener API confirmed: `api.listener.onMessage(cb)` + `api.listener.start()`. Cần `Zalo({selfListen: true})` để echo own messages. |
| Send message | **NOT EXERCISED** (skipped) | API có: `api.sendMessage({msg: text}, threadId, ThreadType.Group | ThreadType.User)` — port từ probe v1 |
| Burst rate-limit | **NOT EXERCISED** (skipped) | Defer Task E1 |

## API changes vs probe v1 — checklist cho implementation

| Probe v1 | v2.1.2 (current) | Tác động code |
|---|---|---|
| `api.fetchGroupInfo(gid)` | `api.getGroupInfo([gid])` (array) | Sửa `resolve_group_owner`, admin /bot-accounts/:id member view |
| `getAllGroups().gridInfoMap` | `getAllGroups().gridVerMap` (map gid→version) | List group cần loop call `getGroupInfo` per gid |
| Member IDs từ `gridInfoMap[gid].memberIDs` | `gridInfoMap[gid].memVerList[].split('_')[0]` | `resolve_group_owner` extract userId từ memVerList |
| Listener `api.listener.on('message',...)` | `api.listener.onMessage(cb)` | Sửa bridge listener attach |
| `Zalo({logging: false})` | Cùng + thêm `{selfListen: true}` nếu cần echo | Bridge config |

## Bytes cần update spec

1. **§10.1 stack table**: row "Channel — Zalo (MVP)" hiện ghi `zlapi-py (port legacy)` → đổi thành:
   `zca-js@^2.1 Node bridge (port từ archive/legacy:src/channels/zalo_bridge, adapt cho v2.1 API)`.
   Note: spec đã có disclaimer "port legacy" — `zlapi-py` chỉ là tên cũ lỗi trong spec text.

2. **§3.4 resolve_group_owner**: thêm note implementation chi tiết:
   ```python
   info = await api.getGroupInfo([chat_id])
   member_ids = [s.split('_', 1)[0] for s in info['gridInfoMap'][chat_id]['memVerList']]
   ```

3. **§2.1.1 capability matrix** Zalo row: confirm `requires_admin_role_for_core = False` (anh đã owner/admin trong group test nhưng `creatorId == own_id` không bắt buộc cho list).

## Open items defer Task E1 implementation

- Listener message capture end-to-end (verify DM, group text, image, mention, reply shape)
- Send group + DM
- Burst 20msg/30s (rate-limit feel)
- Stdin-driven bridge protocol (legacy bridge.js có sẵn, cần adapt v2 API)
- Error/reconnect handling: WS drop, session expire, banned acc

## Risk note

- zca-js có thể continue breaking changes minor → pin version `2.1.x` chính xác trong package.json
- `memberIds` empty bug — nếu sau dùng API khác hoặc Zalo update server, có thể fix → vẫn nên dùng `memVerList` làm canonical
- "Tài khoản bị khóa" placeholder member trong getGroupMembersInfo cho group có deactivated user → filter `accountStatus` trong UI

## Files spike

- `spikes/zalo-2026/login.js` — QR login (legacy, work as-is)
- `spikes/zalo-2026/bridge.js` — legacy bridge (CHƯA test; v2 API change → cần adapt at Task E1)
- `spikes/zalo-2026/probe_group_ops.js` — NEW
- `spikes/zalo-2026/probe_groups_sample.js` — NEW (5 group sample)
- `spikes/zalo-2026/probe_memver.js` — NEW (memVerList shape)
- `spikes/zalo-2026/probe_api_methods.js` — NEW (146 methods listed)
- `spikes/zalo-2026/probe_listener.js` — NEW (connect-only verified)
- `spikes/zalo-2026/package.json` (zca-js@^2.0.0-beta.27 → resolved to 2.1.2)

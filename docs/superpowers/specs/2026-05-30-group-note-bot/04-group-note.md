[← Index](./README.md)

# §4. Group Note (hiện vật cốt lõi)

## 4.1 Tại sao 1 note/group

Không có hiện vật bền vững → mỗi lần Q&A đều start từ message raw →
context tốn, câu trả lời không nhất quán. Có rolling note thì:

- Lịch sử quyết định được bảo tồn (không bị mất trong scroll-back).
- Action item có nơi sống duy nhất.
- Context của LLM Q&A giảm từ ~50k token raw chat xuống ~1k token note
  + retrieval.
- Sếp có UI đọc "tình trạng group" trong 1 màn hình.

## 4.2 Schema 7 section

Section không có content thì ẩn khi render. Header do code template;
LLM fill content. **Không dùng emoji** trong heading — web UI render
status bằng badge/chip, không bằng ký tự hình.

```markdown
# {group_name}
Cập nhật: {iso_timestamp} · {msg_count_7d}/ngày · {status_text}

## Cần sếp xử lý                    (ẩn nếu trống)
- bullet ngắn, việc rõ ràng đang cần sếp action

## Đang focus                        (max 3–5 bullet)
- group đang đẩy chuyện gì hiện tại

## Việc đang mở                      (task list — chủ + hạn)
- [ ] {person} — {task} · {hạn_hoặc_open}
- [ ] {person} — {task} · QUÁ HẠN {Nd}     <!-- web đánh badge "Trễ" -->

## Đang tắc / Rủi ro                 (ẩn nếu trống)
- blocker, việc tắc, risk

## Đã quyết                          (log quyết định, append-only)
- {quyết định} ({attributed_to}, {date})

## Câu hỏi treo                      (ẩn nếu trống)
- câu hỏi mở, visible cho team

## Người active (7d)
- {name} ({count}) · ...

## Lưu trữ
- [{period}](archive link)
```

**Nguyên tắc design:**
- Exception đặt trước (Cần sếp, Đang tắc). Scan top thấy ngay.
- Giá trị bền vững ở dưới. `Đã quyết` là log append-only.
- LLM **không bao giờ** xoá entry trong `Đã quyết`. Chỉ manual edit
  xoá được.
- `Người active` tính từ count message, không phải LLM suy ra.
- Markdown thuần — không emoji, không decorative char. Web UI tô màu
  qua CSS class (xem [§9.0](./09-web-admin.md#90-design-principles)).

## 4.3 Vòng đời update

3 trigger (bất kỳ cái nào queue update):

| Trigger | Khi nào | Lý do |
|---|---|---|
| **Debounce 10 phút** | Group có message trong X phút trước; X phút trôi kể từ message mới nhất | Cuộc trò chuyện đã lắng |
| **Threshold 30 msg** | 30 message mới kể từ lần update note gần nhất | Đừng đợi quá lâu cho group đông |
| **On-demand** | `@bot refresh note` trong group, hoặc nút "Refresh" trên web | User chủ động |

Quy trình update:

```
1. Acquire lock (boss_id, chat_id)   (asyncio.Lock cho MVP)
2. Load group_note.content hiện tại
3. Load message mới từ group_note.last_seen_message_id
4. Build LLM prompt:
   - System: "Update group note. Giữ nguyên section X, Y (đã edit thủ
              công). Chỉ update D, E, F, G. Section 'Đã quyết' chỉ
              append, không xoá."
   - Input: note hiện tại + delta messages
5. LLM (smart tier) emit markdown mới
6. Validate: đủ 7 header (renderer ẩn cái rỗng)
7. UPDATE group_notes SET content, last_seen_message_id, updated_at
   INSERT group_note_versions cho history
8. Release lock
```

## 4.4 Edit thủ công & merge conflict

Web UI hiện note trong markdown editor. Sếp click "Edit", save.

Để lần update tự động sau không ghi đè edit thủ công:

- Khi save, record `manually_edited_sections` (set tên header có content
  khác với version cuối LLM emit).
- Lần auto-update sau, LLM được instruct: "Section {A, B, C} đã edit
  thủ công, giữ nguyên. Chỉ update {D, E, F, G}."
- Granularity = per-section, không per-line. Toggle `Cho bot quản section
  này lại` clear flag cho section đó.

`group_notes.manually_edited_sections` là JSONB array tên section.

## 4.5 Versioning & lưu trữ

- Mỗi lần update INSERT 1 row vào `group_note_versions`. ~vài kB/cái.
- Web hiện timeline version + diff view.
- Sau 30 ngày, version cũ compact: giữ 50 cái gần nhất + monthly snapshot.

## 4.6 Schema DB

```sql
group_notes (
  id                         BIGSERIAL PRIMARY KEY,
  boss_id                    INTEGER NOT NULL REFERENCES users(id),
  provider                   TEXT NOT NULL,
  chat_id                    TEXT NOT NULL,
  group_name                 TEXT,
  content                    TEXT NOT NULL DEFAULT '',
  manually_edited_sections   JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_seen_message_id       BIGINT,
  status                     TEXT NOT NULL DEFAULT 'active',  -- active | quiet | stalled
  msg_count_7d               INTEGER NOT NULL DEFAULT 0,
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, provider, chat_id)
);
CREATE INDEX idx_group_notes_boss ON group_notes(boss_id);

group_note_versions (
  id            BIGSERIAL PRIMARY KEY,
  group_note_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  content       TEXT NOT NULL,
  emitted_by    TEXT NOT NULL,  -- 'llm' | 'user'
  emitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_group_note_versions_note ON group_note_versions(group_note_id, emitted_at DESC);
```

## 4.7 Đã chốt

- Schema section **template-driven** (không hardcode 7 section nữa). Mỗi group chọn 1 template; sếp custom được Phase 1.
- Không emoji trong heading note.
- Section `Đã pin` (manual pin từ chat, [§6.3](./06-agent-layer.md#63-tool-calling)) và `Đã quyết` luôn append-only.

## 4.8 Tham khảo & kỹ thuật

Cách tiếp cận group note giống living document — vài kỹ thuật từ các
bên đang làm tốt hướng này:

### Anthropic — Memory & Projects
- **Living markdown context**: file markdown dài duy trì cross-session,
  agent đọc đầu mỗi lần. Ta đang dùng = `group_notes.content`.
- **Agentic compaction**: khi note dài hơn ngưỡng, dùng LLM smart tier
  rebuild ngắn lại, giữ section append-only (`Đã quyết`). Ta apply ở
  versioning compact (§4.5).
- **Section ownership flag**: phân biệt phần LLM viết vs user edit.
  Ta đã có `manually_edited_sections`. Mở rộng: thêm `freshness_score`
  per-section để LLM biết khi nào re-write (Phase 1).

### Bytedance — Coze / Lark structured docs
- **Structured frontmatter** (YAML head) lưu metadata (`status`,
  `owners`, `tags`) tách khỏi prose. Ta giữ metadata trong cột DB
  riêng (`status`, `msg_count_7d`), không nhúng vào markdown — render
  body sạch hơn.
- **Block ownership**: Coze cho phép từng block có "manageable by AI"
  toggle. Ta granularity = section, đủ cho MVP.

### Apply vào MVP

| Kỹ thuật | Trạng thái |
|---|---|
| Living markdown context | có |
| Per-section manual-edit flag | có (`manually_edited_sections`) |
| Append-only "Đã quyết" | có |
| Versioning + compact lịch sử | có (§4.5) |
| Freshness score per-section | Phase 1 |
| Frontmatter YAML structured | không cần — metadata trong DB |
| AI-managed toggle per-section | có (toggle "cho bot quản lại") |

## 4.9 Note template system

Section schema không hardcode trong code mà khai báo qua **template** — vì
mỗi loại group (sale, dev, đối tác, family) có nhu cầu section khác nhau.
Hardcode 7 section = sau phải refactor khi thêm vertical.

### Schema

```sql
note_templates (
  id              BIGSERIAL PRIMARY KEY,
  name            TEXT NOT NULL,                     -- 'general' | 'sales' | 'partner' | 'dev' | custom
  description     TEXT,
  is_system       BOOLEAN NOT NULL DEFAULT FALSE,    -- seed system template, không cho sửa
  owner_boss_id   INTEGER REFERENCES users(id),      -- NULL cho system; SET cho custom của boss
  sections_json   JSONB NOT NULL,                    -- ordered list of section descriptors
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_note_templates_owner ON note_templates(owner_boss_id);

ALTER TABLE group_notes ADD COLUMN template_id BIGINT REFERENCES note_templates(id);
```

### Section descriptor format

`sections_json` = array, mỗi item:

```json
{
  "key":           "open_tasks",                  // ID nội bộ, dùng trong manually_edited_sections
  "title":         "Việc đang mở",                 // render heading
  "behavior":      "task_list",                    // 'rolling' | 'append_only' | 'task_list' | 'manual_pin' | 'computed'
  "hide_if_empty": true,
  "max_items":     null,
  "llm_hint":      "Task chưa done. Format: [ ] {person} — {task} · {hạn}",
  "writable_by":   "llm"                           // 'llm' | 'user' | 'both'
}
```

`behavior`:
- `rolling`: LLM ghi đè full mỗi update
- `append_only`: chỉ thêm, không xoá (vd `Đã quyết`)
- `task_list`: structured tasks → sync với bảng `action_items` (§13)
- `manual_pin`: chỉ user pin qua tool `pin_message`; LLM không sửa
- `computed`: code tính (vd `Người active (7d)`)

### Seed system templates

```yaml
- name: general
  description: Mặc định, phù hợp đa số group
  sections:
    - {key: needs_boss,    title: "Cần sếp xử lý",   behavior: rolling,     hide_if_empty: true,  writable_by: llm}
    - {key: focus,         title: "Đang focus",       behavior: rolling,     max_items: 5,         writable_by: llm}
    - {key: open_tasks,    title: "Việc đang mở",     behavior: task_list,                          writable_by: both}
    - {key: blocked,       title: "Đang tắc / Rủi ro", behavior: rolling,    hide_if_empty: true,  writable_by: llm}
    - {key: decisions,     title: "Đã quyết",         behavior: append_only,                        writable_by: llm}
    - {key: pinned,        title: "Đã pin",           behavior: manual_pin,  hide_if_empty: true,  writable_by: user}
    - {key: open_questions,title: "Câu hỏi treo",     behavior: rolling,     hide_if_empty: true,  writable_by: llm}
    - {key: active_people, title: "Người active (7d)", behavior: computed,                          writable_by: llm}
    - {key: archive,       title: "Lưu trữ",          behavior: computed,                           writable_by: llm}

- name: sales
  description: Group sale — pipeline, deal, KH
  sections:
    - {key: hot_leads,     title: "Lead nóng",        behavior: rolling,     max_items: 5,         writable_by: llm}
    - {key: open_deals,    title: "Deal đang chạy",   behavior: task_list,                          writable_by: both}
    - {key: needs_boss,    title: "Cần sếp duyệt",    behavior: rolling,     hide_if_empty: true,  writable_by: llm}
    - {key: lost_deals,    title: "Deal mất (7d)",    behavior: append_only, hide_if_empty: true,  writable_by: llm}
    - {key: pinned,        title: "Đã pin",           behavior: manual_pin,  hide_if_empty: true,  writable_by: user}
    - {key: active_people, title: "Người active (7d)", behavior: computed,                          writable_by: llm}

- name: partner
  description: Group đối tác — milestone, deliverable, commitment
  sections:
    - {key: commitments,   title: "Cam kết hai bên",  behavior: append_only,                        writable_by: llm}
    - {key: open_tasks,    title: "Deliverable đang mở", behavior: task_list,                       writable_by: both}
    - {key: blocked,       title: "Đang vướng",       behavior: rolling,     hide_if_empty: true,  writable_by: llm}
    - {key: decisions,     title: "Đã quyết",         behavior: append_only,                        writable_by: llm}
    - {key: pinned,        title: "Đã pin",           behavior: manual_pin,  hide_if_empty: true,  writable_by: user}
```

### Pick template per-group

- Default `general` khi group lần đầu được capture.
- Sếp đổi ở `/groups/:id/settings` — dropdown chọn từ system + custom templates.
- Đổi template = giữ content cũ, re-map section keys mới (best-effort). Section không match → giữ trong "Lưu trữ" tạm.

### LLM prompt cho NoteUpdater nhận template

```
System: Update group note theo template descriptor sau.
        Mỗi section có {key, title, behavior, llm_hint, writable_by}.
        - behavior=rolling: ghi đè full
        - behavior=append_only: chỉ thêm bullet mới, không xoá cũ
        - behavior=task_list: format checklist
        - behavior=manual_pin: BỎ QUA (do user pin tay)
        - behavior=computed: BỎ QUA (do code tính)
        Section trong manually_edited_sections: giữ nguyên.

Template: {sections_json}
Note hiện tại: {markdown}
Delta messages: {recent N messages}

Output: markdown mới đúng thứ tự section, heading theo title.
```

### Custom template (Phase 1)

Phase 1 mở `/settings/templates` cho sếp tự define template. MVP chỉ
system seed + chọn template; không có template editor.

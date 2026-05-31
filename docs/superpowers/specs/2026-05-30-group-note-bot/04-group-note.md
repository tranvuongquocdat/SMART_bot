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

- Schema 7 section cố định cho MVP (không cấu hình per-boss).
- Không emoji trong heading note.

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

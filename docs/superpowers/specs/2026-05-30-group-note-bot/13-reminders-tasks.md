[← Index](./README.md)

# §13. Reminders, tasks, project tracking

Anh muốn vào MVP để **làm base cho follow-task / nhắc task sau**. Cần
build lean — không over-engineer "Project entity" ngay, chỉ làm vừa
đủ để mở đường.

## 13.1 Phạm vi MVP

| Khả năng | MVP | Phase 1 | Phase 2+ |
|---|:-:|:-:|:-:|
| Set reminder qua chat (NL parse) | ✓ | | |
| Set reminder qua web form | ✓ | | |
| Nhắc tại nhóm gốc / DM sếp | ✓ | | |
| List / cancel reminder | ✓ | | |
| Recurring reminder (`mỗi sáng 9h`) | basic (daily/weekly) | full cron | |
| Reminder gắn vào action item | ✓ | | |
| Follow-task: bot tự nhắc lại khi quá hạn | | ✓ | |
| Auto-detect task assign → đề xuất set reminder | | ✓ | |
| Cross-group "Projects" view | ✓ (read-only) | filter/sort | Project entity riêng |
| Project entity (members, milestone, budget) | | | ✓ |

## 13.2 Entity quan hệ

```
group_notes
   │
   │ section "Việc đang mở" có structured action items
   ▼
action_items                     (extract từ note bằng action_item_extract feature)
   │
   │ (optional) reminder gắn với action item
   ▼
scheduled_reminders              (cũng có thể standalone, không link action item)
```

**Không có Project entity riêng.** `/projects` web page là VIEW
aggregate trên group_notes + action_items + scheduled_reminders cross-group.

## 13.3 Schema

```sql
action_items (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  text            TEXT NOT NULL,
  assignee_name   TEXT,                                 -- display name, không resolve
  due_at          TIMESTAMPTZ,                          -- nullable
  status          TEXT NOT NULL DEFAULT 'open',         -- 'open' | 'done' | 'cancelled'
  source          TEXT NOT NULL,                        -- 'note_extract' | 'manual' | 'agent'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_action_items_boss_status ON action_items(boss_id, status);
CREATE INDEX idx_action_items_due ON action_items(boss_id, due_at) WHERE status = 'open';

scheduled_reminders (
  id                BIGSERIAL PRIMARY KEY,
  boss_id           INTEGER NOT NULL REFERENCES users(id),
  text              TEXT NOT NULL,                      -- "Nhắc anh Tân nộp báo cáo"
  due_at            TIMESTAMPTZ NOT NULL,
  scope             TEXT NOT NULL,                      -- 'group' | 'dm'
  provider          TEXT,                               -- nullable cho scope=dm (dùng bất kỳ acc)
  chat_id           TEXT,                               -- nhóm gốc (scope=group) hoặc DM target
  bot_account_id    BIGINT REFERENCES bot_accounts(id), -- acc gửi
  recurring         TEXT,                               -- nullable | 'daily' | 'weekly:mon,wed,fri'
  action_item_id    BIGINT REFERENCES action_items(id), -- nullable, gắn task
  status            TEXT NOT NULL DEFAULT 'pending',    -- 'pending' | 'fired' | 'cancelled' | 'failed'
  fired_at          TIMESTAMPTZ,
  last_error        TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by_op     TEXT NOT NULL                       -- 'in_group_responder' | 'dm_responder' | 'web'
);
CREATE INDEX idx_reminders_due ON scheduled_reminders(due_at, status) WHERE status = 'pending';
CREATE INDEX idx_reminders_boss ON scheduled_reminders(boss_id, status);
```

`action_items` không phải bảng "source of truth" cho task — note
markdown vẫn là canonical (anh có thể edit thẳng note). `action_items`
là **index trích từ note** để query nhanh + gắn reminder. Khi note
re-build, action_item_extract feature re-sync bảng (upsert by stable
hash của text + assignee).

### Default scope resolution

Khi feature `reminder_parse` chạy, scope quyết theo rule:

| Bối cảnh set | Default scope | Override khi |
|---|---|---|
| Trong group (`@bot nhắc...`) | **group** (nhắc tại nhóm gốc) | text có "nhắc riêng tôi" / "DM tôi" / "chỉ tôi" → `dm` |
| Trong DM với sếp | **dm** | text có "nhắc ở nhóm X" / chỉ định group → `group` với chat_id của X |

Rule cứng — không hỏi sếp lại nếu rõ context. LLM chỉ ask clarify khi
ambiguous thực sự (vd sếp nói "nhắc team" trong DM mà có nhiều group team).

## 13.4 Set reminder qua chat

Trong nhóm:

```
@bot nhắc anh Tân nộp báo cáo Q2 chiều thứ 5 lúc 3h

→ InGroupResponder.handle(...)
  → feature=intent_classify (fast) → "set_reminder"
  → feature=reminder_parse (fast) → {
      text: "Nhắc anh Tân nộp báo cáo Q2",
      due_at: "2026-06-04T15:00:00+07:00",   # next Thursday 3pm
      scope: "group",
      target: <chat_id của nhóm hiện tại>
    }
  → tool set_reminder(...)
  → INSERT scheduled_reminders, status=pending
  → reply nhóm: "Đã đặt nhắc T5 4/6 15:00 tại nhóm này."
```

Trong DM:

```
sếp: "nhắc tôi chiều mai 3h gọi đối tác A"

→ DMResponder
  → reminder_parse → {scope: "dm", due_at: ...}
  → INSERT, status=pending, chat_id = sếp's DM chat
  → reply DM: "Đã đặt nhắc mai 15:00 ở đây."
```

## 13.5 Scheduler — ReminderFirer

APScheduler job mỗi 30s:

```python
async def fire_due_reminders():
    now = utc_now()
    due = await reminders_repo.fetch_due(now)            # status=pending and due_at <= now
    for r in due:
        try:
            adapter = channel_for(r.provider or default_provider_of(r.boss_id))
            bot_acc = await bot_accounts_repo.get(r.bot_account_id)
            await adapter.send_text(bot_acc, r.chat_id, format_reminder(r))
            await reminders_repo.mark_fired(r.id, now)
            if r.recurring:
                await reminders_repo.create_next_occurrence(r)
        except Exception as e:
            await reminders_repo.mark_failed(r.id, str(e))
            log.warn(...)
```

- Idempotent: nếu fire xong rồi crash → status='fired' đã commit, không
  gửi lặp.
- Recurring: `daily` / `weekly:<days>`. Khi fire xong, tạo bản kế tiếp
  status=pending. Cancel cha = cancel cả tương lai.
- Cap missed window: nếu `due_at < now - 1h` (server down lâu), gửi kèm
  cảnh báo "Reminder gốc đặt vào 15:00 hôm qua, vừa khôi phục".

## 13.6 List / cancel

DM:
- "nhắc gì sắp tới" → tool `list_reminders(status='pending')` → bot
  trả lời gọn.
- "huỷ cái nhắc về báo cáo Q2" → tool `list_reminders` lọc text →
  match 1 → `cancel_reminder`; nhiều match → bot hỏi clarify (LLM tự xử,
  không hardcode logic).

Web `/reminders` (xem [§9.8](./09-web-admin.md#98-reminders--projects)):
edit due_at, text, scope, target. Cancel = update status.

## 13.7 Projects view (cross-group)

`/projects` chỉ là VIEW. Query aggregate:

```sql
-- per "project" = per group_note
SELECT
  gn.id, gn.group_name, gn.provider, gn.chat_id, gn.updated_at,
  COUNT(*) FILTER (WHERE ai.status = 'open')                 AS open_count,
  COUNT(*) FILTER (WHERE ai.status = 'open' AND ai.due_at < NOW()) AS overdue_count,
  COUNT(DISTINCT r.id) FILTER (WHERE r.status = 'pending')   AS pending_reminders
FROM group_notes gn
LEFT JOIN action_items ai ON ai.group_note_id = gn.id
LEFT JOIN scheduled_reminders r
  ON r.boss_id = gn.boss_id AND r.provider = gn.provider AND r.chat_id = gn.chat_id
WHERE gn.boss_id = $1
GROUP BY gn.id
ORDER BY gn.updated_at DESC;
```

Click row → group detail page (đã có).

Không build "Project membership", "Project owner", "Milestone",
"Budget" — Phase 2 nếu nhu cầu thật.

## 13.8 Đường dài (mở đường, không build MVP)

Schema + agent loop hiện đủ chỗ cho các tính năng sau, không cần
refactor lớn:

- **Follow-task**: scheduler job đọc `action_items` quá hạn → tự tạo
  reminder cho sếp (Phase 1).
- **Stalled-work alert**: feature `stalled_detect` (smart tier) chạy
  cron weekly, đọc note + retrieval → list "việc nói lâu không
  update".
- **Auto-suggest reminder**: khi NoteUpdater extract action item có
  `due_at` → đề xuất sếp set reminder (DM).
- **Project entity riêng**: khi cross-group aggregate không đủ (cần
  member, doc gắn ngoài group note) → thêm bảng `projects` + `project_items`.

## 13.9 Đã chốt

- Reminder vào MVP, scope = group / dm; recurring basic (daily, weekly).
- `action_items` là index trích từ note, không source of truth.
- Projects = view, không entity.
- Follow-task + auto-suggest → Phase 1, schema đã sẵn chỗ.

#!/usr/bin/env bash
# Seed mock data for the local boss test account (boss@local.test, id=2)
# so the admin dashboard has groups, tasks, reminders, messages, decisions
# to render. Idempotent: clears existing demo rows for boss=2 first.
set -euo pipefail

BOSS_ID="${BOSS_ID:-2}"
DB_URL="${DATABASE_URL:-postgresql://smart:smart@localhost:5433/smart_bot}"

echo "→ Seeding demo data for boss_id=$BOSS_ID …"

PGPASSWORD=smart psql "$DB_URL" -v ON_ERROR_STOP=1 <<SQL
BEGIN;

-- Wipe prior demo rows for this boss (safe — only touches boss=$BOSS_ID).
DELETE FROM decisions          WHERE group_id IN (SELECT id FROM group_notes WHERE boss_id=$BOSS_ID);
DELETE FROM scheduled_reminders WHERE boss_id=$BOSS_ID;
DELETE FROM action_items        WHERE boss_id=$BOSS_ID;
DELETE FROM messages            WHERE boss_id=$BOSS_ID;
DELETE FROM group_notes         WHERE boss_id=$BOSS_ID;

-- 5 groups (mix zalo / telegram), updated_at staggered so "recent" sorts nicely.
INSERT INTO group_notes (boss_id, provider, chat_id, group_name, msg_count_7d, updated_at)
VALUES
  ($BOSS_ID, 'zalo',     'zalo-grp-101', 'Marketing Q3',        42, now() - interval '3 minutes'),
  ($BOSS_ID, 'zalo',     'zalo-grp-102', 'Sales VN',            28, now() - interval '47 minutes'),
  ($BOSS_ID, 'telegram', 'tg-grp-201',   'Product launch H2',   17, now() - interval '2 hours'),
  ($BOSS_ID, 'zalo',     'zalo-grp-103', 'Operations',          11, now() - interval '5 hours'),
  ($BOSS_ID, 'telegram', 'tg-grp-202',   'Customer support',     8, now() - interval '1 day');

-- 6 action items (4 due today, 2 due upcoming), all open.
WITH g AS (SELECT id, group_name FROM group_notes WHERE boss_id=$BOSS_ID)
INSERT INTO action_items (boss_id, group_note_id, text, assignee_name, due_at, status, source, created_at)
SELECT $BOSS_ID, g.id, t.text, t.assignee, t.due, 'open', 'demo', now() - interval '1 day' * t.age
FROM (VALUES
  ('Review báo cáo Q2',           'Anh Tâm',   (now()::date + interval '14 hours'),                  0),
  ('Họp team marketing',          'Chị Linh',  (now()::date + interval '15 hours 30 minutes'),       0),
  ('Duyệt budget tháng 7',         NULL,       (now()::date + interval '17 hours'),                  1),
  ('Phản hồi email khách VIP',     'Bot',      (now()::date + interval '23 hours'),                  0),
  ('Chuẩn bị slide kickoff H2',    'Anh Tuấn', (now()::date + interval '2 days'),                    2),
  ('Ký hợp đồng đối tác Z',        NULL,       (now()::date + interval '4 days'),                    3)
) AS t(text, assignee, due, age)
JOIN g ON g.group_name IN ('Marketing Q3','Sales VN','Operations','Product launch H2');

-- 3 scheduled reminders pending.
INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, status, created_by_op, created_at)
VALUES
  ($BOSS_ID, 'Nhắc anh Tân lịch chiếu thứ 3',  now() + interval '6 hours',  'personal', 'pending', 'demo', now() - interval '2 hours'),
  ($BOSS_ID, 'Nhắc cả nhóm review demo H2',    now() + interval '1 day',    'group',    'pending', 'demo', now() - interval '5 hours'),
  ($BOSS_ID, 'Nhắc check báo cáo tài chính',   now() + interval '2 days',   'personal', 'pending', 'demo', now() - interval '1 day');

-- Messages spread across last 30 days (current period).
-- ~280 messages, decreasing density older — gives a strong "messages" count.
WITH g AS (SELECT id, provider, chat_id FROM group_notes WHERE boss_id=$BOSS_ID)
INSERT INTO messages (boss_id, provider, chat_id, chat_type, sender_name, text, ts)
SELECT $BOSS_ID, g.provider, g.chat_id, 'group',
       'User #' || (1 + (s % 5))::text,
       'Demo message ' || s::text,
       now() - (random() * interval '30 days')
FROM g
CROSS JOIN generate_series(1, 56) AS s;

-- Messages 60→30d ago (prev period) — smaller, so delta is positive.
WITH g AS (SELECT id, provider, chat_id FROM group_notes WHERE boss_id=$BOSS_ID)
INSERT INTO messages (boss_id, provider, chat_id, chat_type, sender_name, text, ts)
SELECT $BOSS_ID, g.provider, g.chat_id, 'group',
       'User #' || (1 + (s % 5))::text,
       'Demo old ' || s::text,
       now() - interval '30 days' - (random() * interval '30 days')
FROM g
CROSS JOIN generate_series(1, 38) AS s;

-- Action items in prev 30d (already-closed older ones, for delta).
WITH g AS (SELECT id FROM group_notes WHERE boss_id=$BOSS_ID LIMIT 1)
INSERT INTO action_items (boss_id, group_note_id, text, assignee_name, status, source, created_at)
SELECT $BOSS_ID, g.id, 'Việc cũ ' || s::text, NULL, 'done', 'demo',
       now() - interval '30 days' - (random() * interval '30 days')
FROM g, generate_series(1, 5) AS s;

-- Reminders in prev 30d.
INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, status, created_by_op, created_at)
SELECT $BOSS_ID, 'Nhắc cũ ' || s::text,
       now() - interval '30 days' + interval '1 day',
       'personal', 'fired', 'demo',
       now() - interval '30 days' - (random() * interval '30 days')
FROM generate_series(1, 4) AS s;

-- Decisions: 4 in last 30d, 2 in prev 30d.
WITH g AS (SELECT id FROM group_notes WHERE boss_id=$BOSS_ID)
INSERT INTO decisions (group_id, text, decided_by, created_at)
SELECT g.id, d.text, d.who, d.ts
FROM g
CROSS JOIN (VALUES
  ('Chọn nhà cung cấp Y cho H2',       'Boss',    now() - interval '3 days'),
  ('Tăng ngân sách MKT thêm 15%',       'Boss',    now() - interval '8 days'),
  ('Dời deadline launch sang 30/8',      'Boss',    now() - interval '12 days'),
  ('Approve hire 2 PM cho team Product','Boss',    now() - interval '20 days'),
  ('Cũ: Đổi vendor cũ',                  'Boss',    now() - interval '40 days'),
  ('Cũ: Cắt feature low-priority',       'Boss',    now() - interval '55 days')
) AS d(text, who, ts)
WHERE g.id = (SELECT MIN(id) FROM group_notes WHERE boss_id=$BOSS_ID);

COMMIT;

\echo '---'
\echo 'Demo data seeded. Summary for boss_id=$BOSS_ID:'
SELECT 'groups'   AS kind, count(*) FROM group_notes         WHERE boss_id=$BOSS_ID
UNION ALL SELECT 'tasks (open)',   count(*) FROM action_items        WHERE boss_id=$BOSS_ID AND status='open'
UNION ALL SELECT 'reminders',      count(*) FROM scheduled_reminders WHERE boss_id=$BOSS_ID
UNION ALL SELECT 'messages 30d',   count(*) FROM messages            WHERE boss_id=$BOSS_ID AND ts >= now() - interval '30 days'
UNION ALL SELECT 'messages 60-30d',count(*) FROM messages            WHERE boss_id=$BOSS_ID AND ts < now() - interval '30 days' AND ts >= now() - interval '60 days'
UNION ALL SELECT 'decisions 30d',  count(*) FROM decisions d JOIN group_notes gn ON gn.id=d.group_id WHERE gn.boss_id=$BOSS_ID AND d.created_at >= now() - interval '30 days';
SQL

echo "✓ Done."

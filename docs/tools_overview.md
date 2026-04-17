# Tools Overview — 2026-04-17

**Branch:** `feature/person-identity-harvesting`
**Total registered tools:** 57 (all entries in `TOOL_DEFINITIONS` in [`src/tools/__init__.py`](../src/tools/__init__.py))
**Consistency:** `TOOL_DEFINITIONS` and `_dispatch_tool` are fully in sync — no gaps.

---

## Table of Contents

1. [Task](#1-task) — 5 tools
2. [People](#2-people) — 7 tools
3. [Project](#3-project) — 6 tools
4. [Reminder](#4-reminder) — 4 tools
5. [Communication](#5-communication) — 7 tools _(4 identity tools newly added in this branch)_
6. [Note / Idea](#6-note--idea) — 4 tools
7. [Group](#7-group) — 1 tool
8. [Workspace](#8-workspace) — 2 tools
9. [Approval](#9-approval) — 3 tools
10. [Summary / Search](#10-summary--search) — 7 tools
11. [Reset](#11-reset) — 3 tools
12. [Review Schedule Config](#12-review-schedule-config) — 4 tools
13. [Misc](#13-misc) — 4 tools
14. [Gaps / Questions](#gaps--questions)

---

## 1. Task

**5 tools** — [`src/tools/tasks.py`](../src/tools/tasks.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `create_task` | Tạo task mới. Gọi get_person trước để check effort_score. Nếu > 0.8, hỏi xác nhận. | `name` | Writes to Lark (tasks table); embeds to Qdrant (background); sends Telegram DM to assignee(s); logs to `outbound_messages` (DB) | [tasks.py:165](../src/tools/tasks.py#L165) |
| `list_tasks` | Liệt kê task có lọc. Gọi không tham số = tất cả task. | _(none)_ | Reads Lark (tasks table); supports multi-workspace via `workspace_ids` | [tasks.py:247](../src/tools/tasks.py#L247) |
| `update_task` | Cập nhật task. Non-boss changes (except done/cancel) are routed through approval flow. | `search_keyword` | Writes to Lark; re-embeds to Qdrant; may send Telegram DM (boss notify, assignee notify, group notify); writes `pending_approvals` DB if non-boss | [tasks.py:284](../src/tools/tasks.py#L284) |
| `delete_task` | Xóa task. LUÔN hỏi sếp xác nhận trước khi gọi. | `search_keyword` | Deletes from Lark; deletes from Qdrant | [tasks.py:400](../src/tools/tasks.py#L400) |
| `search_tasks` | Tìm task bằng semantic search (tìm theo nghĩa). | `query` | Reads Qdrant then cross-references Lark (read-only) | [tasks.py:418](../src/tools/tasks.py#L418) |

---

## 2. People

**7 tools** — [`src/tools/people.py`](../src/tools/people.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `add_people` | Thêm người mới vào hệ thống nhân sự. | `name` | Writes to Lark (people table); inserts into `people_map` SQLite if `chat_id` provided | [people.py:57](../src/tools/people.py#L57) |
| `get_people` | Xem thông tin chi tiết — fat return: profile + tasks + effort_score + last DM + has_dmd_bot flag. | `search_name` | Reads Lark (people + tasks tables); reads `outbound_messages` DB | [people.py:98](../src/tools/people.py#L98) |
| `list_people` | Liệt kê danh sách nhân sự, có thể lọc theo nhóm hoặc loại. | _(none)_ | Reads Lark (people table) | [people.py:182](../src/tools/people.py#L182) |
| `update_people` | Cập nhật thông tin của một người trong hệ thống. | `search_name` | Writes to Lark (people table) | [people.py:200](../src/tools/people.py#L200) |
| `delete_people` | Xóa người khỏi hệ thống. LUÔN hỏi sếp xác nhận trước. | `search_name` | Deletes from Lark (people table); deletes from `people_map` SQLite if Chat ID exists | [people.py:246](../src/tools/people.py#L246) |
| `check_effort` | Kiểm tra workload của một người: tasks đang làm, xung đột deadline. GỌI TRƯỚC khi giao task. | `assignee` | Reads Lark (tasks table); supports multi-workspace | [people.py:371](../src/tools/people.py#L371) |
| `check_team_engagement` | Kiểm tra mức độ tương tác của từng thành viên: ai đã nhắn, ai chưa, ai overload. | _(none)_ | Reads Lark (people + tasks tables); reads `outbound_messages` DB | [people.py:315](../src/tools/people.py#L315) |

---

## 3. Project

**6 tools** — [`src/tools/projects.py`](../src/tools/projects.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `create_project` | Tạo dự án mới. Status mặc định là 'Chưa bắt đầu'. | `name` | Writes to Lark (projects table) | [projects.py:64](../src/tools/projects.py#L64) |
| `get_project` | Xem thông tin chi tiết dự án kèm danh sách task và tiến độ %. | `search_name` | Reads Lark (projects + tasks tables) | [projects.py:90](../src/tools/projects.py#L90) |
| `list_projects` | Liệt kê tất cả dự án, có thể lọc theo trạng thái. | _(none)_ | Reads Lark (projects table) | [projects.py:137](../src/tools/projects.py#L137) |
| `update_project` | Cập nhật thông tin dự án. | `search_name` | Writes to Lark (projects table) | [projects.py:169](../src/tools/projects.py#L169) |
| `delete_project` | Xóa dự án. LUÔN hỏi sếp xác nhận trước. | `search_name` | Deletes from Lark (projects table) | [projects.py:209](../src/tools/projects.py#L209) |
| `get_project_report` | Tạo báo cáo tổng quan dự án bằng LLM: % tiến độ, blockers, deadlines sắp tới. | `project` | Reads Lark (tasks table); calls LLM (OpenAI) to generate report | [summary.py:156](../src/tools/summary.py#L156) |

---

## 4. Reminder

**4 tools** — [`src/tools/reminder.py`](../src/tools/reminder.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `create_reminder` | Tạo nhắc nhở vào một thời điểm cụ thể. Có thể nhắc sếp hoặc người khác. | `content`, `remind_at` | Writes to SQLite (`reminders` table); optionally syncs to Lark (background); resolves target via Lark people lookup | [reminder.py:52](../src/tools/reminder.py#L52) |
| `list_reminders` | Liệt kê nhắc nhở (pending/done/all). Gọi trước khi nói 'không có reminder'. | _(none)_ | Reads SQLite (`reminders` table) | [reminder.py:113](../src/tools/reminder.py#L113) |
| `update_reminder` | Sửa nhắc nhở theo ID (lấy từ list_reminders). | `reminder_id` | Writes to SQLite (`reminders` table); resolves target via Lark if `target` param given | [reminder.py:139](../src/tools/reminder.py#L139) |
| `delete_reminder` | Xóa nhắc nhở theo ID. | `reminder_id` | Deletes from SQLite (`reminders` table) | [reminder.py:181](../src/tools/reminder.py#L181) |

---

## 5. Communication

**7 tools** — [`src/tools/communication.py`](../src/tools/communication.py)

> Tools `resolve_person`, `link_contact_to_person`, `list_unlinked_contacts`, `get_group_admins` are newly added in branch `feature/person-identity-harvesting`.

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `send_dm` | Gửi tin nhắn riêng (DM) cho một người trong team theo tên. Tự động log vào lịch sử liên lạc. | `to`, `content` | Sends Telegram DM; writes to `outbound_messages` DB; identity resolution via `identity.resolve_candidates()` | [communication.py:49](../src/tools/communication.py#L49) |
| `broadcast` | Gửi thông báo hàng loạt cho nhiều người qua DM cá nhân. | `message` | Sends Telegram DM to each target; writes to `outbound_messages` DB; reads Lark (people table) | [communication.py:92](../src/tools/communication.py#L92) |
| `get_communication_log` | Tra lịch sử tất cả tin nhắn bot đã chủ động gửi. GỌI TRƯỚC khi trả lời 'đã nhắn X chưa'. | _(none)_ | Reads `outbound_messages` DB + `messages` DB (DM thread); surfaces unlinked candidates if person has no Chat ID | [communication.py:168](../src/tools/communication.py#L168) |
| `resolve_person` | Tra tất cả ứng viên người khớp query từ mọi nguồn (lark_people, bosses, memberships, seen_contacts). GỌI TRƯỚC khi trả 'không tìm thấy X'. | `query` | Read-only; calls `identity.resolve_candidates()` | [communication.py:272](../src/tools/communication.py#L272) |
| `link_contact_to_person` | Gắn chat_id vào trường Chat ID của 1 Lark People record đang thiếu. Fails loud nếu record đã có Chat ID khác. | `chat_id`, `lark_record_id` | Writes to Lark (people table — Chat ID field); inserts into `people_map` SQLite | [communication.py:327](../src/tools/communication.py#L327) |
| `list_unlinked_contacts` | Liệt kê chat_id bot đã thấy trong group/DM nhưng CHƯA gắn vào Lark People record nào. | _(none)_ | Reads `seen_contacts` SQLite; reads Lark (people table) to diff | [communication.py:404](../src/tools/communication.py#L404) |
| `get_group_admins` | Trả danh sách admin của group hiện tại kèm chat_id. Chỉ chạy trong group context. | _(none)_ | Calls Telegram API (`getChatAdministrators`); read-only | [communication.py:454](../src/tools/communication.py#L454) |

> **Legacy note:** `send_message` (in cluster [Misc](#13-misc)) is an older, simpler DM tool that only looks up Lark people and does NOT log to `outbound_messages`. `send_dm` is the preferred successor.

---

## 6. Note / Idea

**4 tools** — [`src/tools/note.py`](../src/tools/note.py), [`src/tools/ideas.py`](../src/tools/ideas.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `update_note` | Lưu ghi chú nội bộ (ghi đè toàn bộ note cũ). Dùng khi cần reorganize stale content. | `note_type`, `ref_id`, `content` | Writes to `notes` SQLite; embeds to Qdrant `notes_{boss_chat_id}` (background) | [note.py:30](../src/tools/note.py#L30) |
| `get_note` | Đọc ghi chú nội bộ đã lưu về người/dự án/nhóm. | `note_type`, `ref_id` | Reads `notes` SQLite | [note.py:41](../src/tools/note.py#L41) |
| `append_note` | Add new information to an existing note without overwriting. Preferred over `update_note` for incremental updates. | `note_type`, `ref_id`, `content` | Reads then writes `notes` SQLite; embeds combined content to Qdrant `notes_{boss_chat_id}` (background) | [note.py:52](../src/tools/note.py#L52) |
| `create_idea` | Lưu ý tưởng nhanh vào hệ thống. | `content` | Writes to Lark (ideas table); embeds to Qdrant `notes_{boss_chat_id}` (background) | [ideas.py:9](../src/tools/ideas.py#L9) |

---

## 7. Group

**1 tool** — [`src/tools/group.py`](../src/tools/group.py)

> Note: `summarize_group_conversation`, `update_group_note`, and `broadcast_to_group` are implemented in `group.py` but are **not** registered in `TOOL_DEFINITIONS` — they are internal helpers only.

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `manage_group` | Manage the Telegram group: invite, rename, pin/unpin, kick, set description, generate invite link. Requires bot to be admin. | `action` | Calls Telegram Bot API (admin actions); reads Lark people table for invite/kick; may send Telegram messages | [group.py:84](../src/tools/group.py#L84) |

**`action` values:** `invite` \| `rename` \| `pin` \| `unpin` \| `kick` \| `set_description` \| `invite_link`

---

## 8. Workspace

**2 tools** — [`src/tools/workspace.py`](../src/tools/workspace.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `set_language` | Persist the language preference for this user. | `language_code` | Writes to `memberships` SQLite; if sender is boss, also writes to `bosses` table | [workspace.py:8](../src/tools/workspace.py#L8) |
| `switch_workspace` | Chuyển workspace đang hoạt động. Lưu vào DB lâu dài. | _(none — `workspace` or `boss_id` recommended)_ | Reads all workspaces; writes `active_workspace_id` to `memberships` SQLite | [workspace.py:26](../src/tools/workspace.py#L26) |

---

## 9. Approval

**3 tools** — [`src/tools/memory.py`](../src/tools/memory.py), [`src/tools/tasks.py`](../src/tools/tasks.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `list_pending_approvals` | Lists all pending approvals: task change requests from members and workspace join requests. | _(none)_ | Reads `pending_approvals` + `memberships` SQLite | [memory.py:22](../src/tools/memory.py#L22) |
| `approve_task_change` | Approve a pending task change request from a member. | `approval_id` | Writes to Lark (task record); updates `pending_approvals` SQLite; sends Telegram DM to requester; optionally broadcasts to group | [tasks.py:439](../src/tools/tasks.py#L439) |
| `reject_task_change` | Reject a pending task change request from a member. | `approval_id` | Updates `pending_approvals` SQLite; sends Telegram DM to requester; optionally broadcasts to group | [tasks.py:496](../src/tools/tasks.py#L496) |

---

## 10. Summary / Search

**7 tools** — [`src/tools/summary.py`](../src/tools/summary.py), [`src/tools/search.py`](../src/tools/search.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `get_summary` | Tổng hợp báo cáo task theo ngày hoặc tuần. | `summary_type` (`today`\|`week`) | Reads Lark (tasks table); supports multi-workspace | [summary.py:22](../src/tools/summary.py#L22) |
| `get_workload` | Xem workload theo người — task đang hoạt động. Default `workspace_ids='all'` để thấy tổng thật sự. | _(none)_ | Reads Lark (tasks table) across workspaces | [summary.py:99](../src/tools/summary.py#L99) |
| `get_project_report` | Tạo báo cáo tổng quan dự án bằng LLM. _(Listed under [Project](#3-project) cluster as well.)_ | `project` | Reads Lark (tasks table); calls LLM (OpenAI) | [summary.py:156](../src/tools/summary.py#L156) |
| `search_history` | Tìm trong lịch sử chat bằng semantic search. scope: `current_chat`\|`all`. | `query` | Reads Qdrant (`messages_{boss_chat_id}` collection) | [search.py:40](../src/tools/search.py#L40) |
| `search_notes` | Tìm kiếm ngữ nghĩa trong ghi chú và ý tưởng đã lưu. note_type: personal\|group\|project\|idea\|all. | `query` | Reads Qdrant (`notes_{boss_chat_id}` collection) | [search.py:8](../src/tools/search.py#L8) |
| `check_effort` | Kiểm tra workload của một người, phát hiện xung đột deadline. _(Listed under [People](#2-people) cluster as well.)_ | `assignee` | Reads Lark (tasks table) | [people.py:371](../src/tools/people.py#L371) |
| `check_team_engagement` | Kiểm tra mức độ tương tác của từng thành viên với bot. _(Listed under [People](#2-people) cluster as well.)_ | _(none)_ | Reads Lark + `outbound_messages` DB | [people.py:315](../src/tools/people.py#L315) |

---

## 11. Reset

**3 tools** — [`src/tools/reset.py`](../src/tools/reset.py)

> Three-step confirmation flow: `initiate_reset` → `confirm_reset_step1` → `execute_reset`. State stored in `sessions` SQLite table (10-minute TTL for step 1, 5-minute TTL for step 2).

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `initiate_reset` | Start the workspace reset flow. Only call when boss clearly wants to delete all workspace data. | _(none)_ | Writes `reset_step` session to SQLite | [reset.py:25](../src/tools/reset.py#L25) |
| `confirm_reset_step1` | Step 2: validate the company name boss typed. | `user_input` | Reads then writes/deletes `sessions` SQLite | [reset.py:45](../src/tools/reset.py#L45) |
| `execute_reset` | Final step: execute nuclear deletion after boss types confirmation phrase. | `confirmation` | **DESTRUCTIVE:** deletes Lark Base (all tables); deletes all SQLite rows (notes, reminders, tasks, people, messages, etc.); deletes Qdrant collections; sends Telegram DM to all members | [reset.py:69](../src/tools/reset.py#L69) |

---

## 12. Review Schedule Config

**4 tools** — [`src/tools/review_config.py`](../src/tools/review_config.py)

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `add_review_schedule` | Thêm lịch review tự động (briefing sáng, tổng kết chiều, hoặc tuỳ chỉnh). | `cron_time` (HH:MM) | Writes to `scheduled_reviews` SQLite; optionally sets `group_chat_id` for `group_brief` | [review_config.py:19](../src/tools/review_config.py#L19) |
| `list_review_schedules` | Xem danh sách lịch review tự động đang được cấu hình. | _(none)_ | Reads `scheduled_reviews` SQLite | [review_config.py:51](../src/tools/review_config.py#L51) |
| `toggle_review` | Bật hoặc tắt một lịch review theo ID. | `review_id`, `enabled` | Writes `enabled` flag in `scheduled_reviews` SQLite | [review_config.py:64](../src/tools/review_config.py#L64) |
| `delete_review_schedule` | Xoá một lịch review theo ID. LUÔN hỏi xác nhận. | `review_id` | Deletes from `scheduled_reviews` SQLite | [review_config.py:74](../src/tools/review_config.py#L74) |

---

## 13. Misc

**4 tools** — various files

| Name | Description | Required params | Side effects | File:line |
|------|-------------|-----------------|--------------|-----------|
| `web_search` | Tìm kiếm thông tin trên web. Uses DuckDuckGo Instant Answer API. | `query` | HTTP GET to `api.duckduckgo.com` (external); no writes | [web_search.py:7](../src/tools/web_search.py#L7) |
| `escalate_to_advisor` | Chuyển sang Cố vấn chiến lược cho phân tích tổng thể. KHÔNG gọi cho CRUD đơn giản. | `reason` | Returns sentinel `__ESCALATE__` to the agent loop — triggers advisor mode | [\_\_init\_\_.py:1222](../src/tools/__init__.py#L1222) |
| `send_message` | Gửi tin nhắn Telegram thay sếp. Legacy tool — looks up Chat ID from Lark only, no outbound log. Prefer `send_dm`. | `to`, `content` | Sends Telegram DM; reads Lark (people table); NO outbound log | [messaging.py:8](../src/tools/messaging.py#L8) |
| `review_config` | _(module name — not a single tool)_ | — | — | — |

> Note: `review_config` above refers to the module; the individual tools are in cluster [12](#12-review-schedule-config).

---

## Gaps / Questions

_(To be filled in — em sẽ lấp sau)_

- `send_message` (messaging.py) vs `send_dm` (communication.py): two tools do the same thing — `send_message` is older, has no outbound log, no identity resolution. Consider deprecating `send_message` from `TOOL_DEFINITIONS` and routing all DMs through `send_dm`.

- `group.py` implements `summarize_group_conversation`, `update_group_note`, and `broadcast_to_group` — these are real, working functions but **not** registered in `TOOL_DEFINITIONS`. Intentional omission or oversight?

- `memory.py::search_history` (line 8) is a legacy version of the search tool — the active routing uses `search.py::search_history`. The old function in `memory.py` is dead code (not reachable via dispatch).

- `get_people` dispatches to `people.get_person()` (not `get_people()`). The alias `get_person` is also handled in dispatch (`case "get_people" | "get_person"`), but only `get_people` appears in `TOOL_DEFINITIONS`.

"""
Scheduler: morning review, evening summary, deadline alerts, reminders.
Loops through all bosses for each scheduled job.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.config import Settings
from src.context import ChatContext
from src.channels import telegram_singleton as telegram
from src.infrastructure import lark_client as lark

logger = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None
_settings: Settings | None = None


def _make_ctx(boss: dict) -> ChatContext:
    """Tao ChatContext cho scheduler jobs."""
    return ChatContext(
        sender_chat_id=boss["chat_id"],
        sender_name=boss["name"],
        sender_type="boss",
        boss_chat_id=boss["chat_id"],
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        lark_table_reminders=boss.get("lark_table_reminders", ""),
        lark_table_notes=boss.get("lark_table_notes", ""),
        chat_id=boss["chat_id"],
        is_group=False,
        group_name="",
        messages_collection=f"messages_{boss['chat_id']}",
        tasks_collection=f"tasks_{boss['chat_id']}",
    )


async def _morning_review():
    """8h sang: Advisor chay smart daily review cho moi sep."""
    from src.advisor import run_daily_review
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            review = await run_daily_review(ctx, _settings)
            await telegram.send(boss["chat_id"], review)
            logger.info("[scheduler] Morning review sent to %s", boss["name"])
        except Exception:
            logger.exception("[scheduler] Morning review failed for %s", boss["name"])


async def _evening_summary():
    """17h: tong ket ngay."""
    from src.services.summary_service import get_summary
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            text = await get_summary(ctx, "today")
            await telegram.send(boss["chat_id"], f"*Tong ket cuoi ngay:*\n\n{text}")
        except Exception:
            logger.exception("[scheduler] Evening summary failed for %s", boss["name"])


async def _resolve_task_targets(
    task: dict, person: dict | None, boss_chat_id: str | None = None,
) -> tuple[str | None, str | None]:
    """For a task, return (primary_target, fallback_target).

    Routing rules:
      - Task created in a group (has "Group ID") → primary = group; assignee DM
        is a courtesy CC, only sent when their Chat ID is known.
      - Task from DM (no Group ID) → primary = assignee DM (when known).
      - When the assignee has no Chat ID AND task has no Group ID, both are None.

    C1 channel-isolation: when `boss_chat_id` is supplied and the boss has a
    `primary_channel` set, the assignee DM is dropped (set to None) if the
    assignee lives on a different channel — group fallback then kicks in.
    """
    from src.utils.chat_id_resolver import (
        resolve_lark_chat_id, is_target_on_boss_channel,
    )

    group_id = task.get("Group ID")
    assignee_id: str | None = None
    if person and person.get("Chat ID"):
        assignee_id = await resolve_lark_chat_id(
            person["Chat ID"], person.get("Tên", "") or "",
        )

    # Drop cross-channel DM so a Zalo boss never leaks across to Telegram.
    if assignee_id and boss_chat_id:
        if not await is_target_on_boss_channel(boss_chat_id, assignee_id):
            assignee_id = None

    if group_id:
        # Group is the primary surface; assignee DM is a courtesy CC.
        return str(group_id), assignee_id
    return assignee_id, None


async def _check_deadlines():
    """9h30: Check deadline sap toi -> nhan nguoi duoc giao."""
    from datetime import date, datetime, timedelta

    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
            people = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
            people_map = {p.get("Tên", "").lower(): p for p in people}

            tomorrow = date.today() + timedelta(days=1)
            tomorrow_ms = int(datetime.combine(tomorrow, datetime.min.time()).timestamp() * 1000)
            tomorrow_end = tomorrow_ms + 86400 * 1000

            today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)

            for r in records:
                if r.get("Status") not in ("Mới", "Đang làm"):
                    continue
                dl = r.get("Deadline")
                if not isinstance(dl, (int, float)):
                    continue

                assignee_name = r.get("Assignee", "").lower()
                person = people_map.get(assignee_name)
                task_name = r.get("Tên task", "?")
                primary, fallback = await _resolve_task_targets(r, person, boss["chat_id"])

                # Deadline tomorrow -> nhac primary (group nếu task từ group,
                # ngược lại DM assignee). Có CC nếu primary là group.
                if tomorrow_ms <= dl < tomorrow_end:
                    if primary:
                        await telegram.send(
                            primary,
                            f"Nhac nho: Task '{task_name}' deadline ngay mai!"
                        )
                    if fallback:
                        await telegram.send(
                            fallback,
                            f"Nhac nho: Task '{task_name}' deadline ngay mai!"
                        )

                # Overdue -> nhac primary (group hoặc assignee DM) + bao boss
                if dl < today_ms:
                    if primary:
                        await telegram.send(
                            primary,
                            f"Task '{task_name}' da QUA HAN! Cap nhat tien do nhe."
                        )
                    if fallback:
                        await telegram.send(
                            fallback,
                            f"Task '{task_name}' da QUA HAN! Cap nhat tien do nhe."
                        )
                    await telegram.send(
                        boss["chat_id"],
                        f"Task qua han: '{task_name}' ({r.get('Assignee', 'N/A')})"
                    )
        except Exception:
            logger.exception("[scheduler] Deadline check failed for %s", boss["name"])


_NO_REPLY_GRACE_HOURS = 3


async def _check_no_reply_reminders():
    """E2 — escalate to boss when a target ignored a reminder for too long.

    Every 30 minutes: scan `outbound_messages` for `trigger_type='reminder'`
    older than _NO_REPLY_GRACE_HOURS that haven't been escalated yet. For
    each, look at the `messages` table: if no inbound from the target since
    the fire timestamp → DM the boss and flip escalated=1. If the target
    did reply, just mark escalated=1 (resolved, no spam).
    """
    try:
        rows = await db.get_unescalated_reminders_older_than(_NO_REPLY_GRACE_HOURS)
    except Exception:
        logger.exception("[scheduler] no-reply scan failed")
        return

    for row in rows:
        try:
            replied = await db.has_inbound_after(row["to_chat_id"], row["created_at"])
            if not replied:
                msg = (
                    f"_{row.get('to_name') or 'Người được nhắc'}_ chưa phản hồi tin "
                    f"nhắc em đã gửi ~{_NO_REPLY_GRACE_HOURS}h trước:\n"
                    f"> {row['content'][:200]}\n\n"
                    f"Anh có muốn em hỏi lại không?"
                )
                await telegram.send(row["boss_chat_id"], msg)
            await db.mark_outbound_escalated(row["id"])
        except Exception:
            logger.exception(
                "[scheduler] no-reply escalation for outbound id=%s failed",
                row.get("id"),
            )


async def _check_reminders():
    """Moi phut: check reminders den gio -> qua agent LLM de gui loi nhac tu nhien.

    After sending, mark done in SQLite AND push Trạng thái=done to the matching
    Lark row. Without the Lark write, the next reverse-sync (every 30s) would
    read Lark's stale 'pending' and clobber SQLite back to pending, causing the
    reminder to re-fire on every minute boundary.
    """
    from src import agent  # noqa: PLC0415

    reminders = await db.get_due_reminders()
    for r in reminders:
        try:
            # send_reminder owns the SQLite mark-done transition (right
            # after main delivery succeeds). Scheduler only owns the
            # Lark write-back so the UI flips too.
            await agent.send_reminder(r, _settings)
            lark_rec_id = r.get("lark_record_id")
            if lark_rec_id:
                boss = await db.get_boss(r["boss_chat_id"])
                tbl = (boss or {}).get("lark_table_reminders", "")
                base = (boss or {}).get("lark_base_token", "")
                if tbl and base:
                    try:
                        await lark.with_retry(lambda: lark.update_record(
                            base, tbl, lark_rec_id, {"Trạng thái": "done"},
                        ))
                    except Exception:
                        logger.warning(
                            "[scheduler] could not flip Lark Trạng thái=done for reminder %d",
                            r["id"], exc_info=True,
                        )
            logger.info("[scheduler] Reminder %d sent", r["id"])
        except Exception:
            logger.exception("[scheduler] Reminder %d failed", r["id"])


async def _check_deadline_push():
    """Moi 30p: push assignee khi task con 24h hoac 2h toi deadline."""
    from datetime import datetime, timezone
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    h24_ms = now_ms + 24 * 3600 * 1000
    h2_ms  = now_ms + 2  * 3600 * 1000

    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            tasks = await lark.search_records(boss["lark_base_token"], boss["lark_table_tasks"])
            open_tasks = [
                t for t in tasks
                if t.get("Status") not in ("Hoàn thành", "Huỷ", "Done", "Cancelled")
            ]
            for task in open_tasks:
                deadline = task.get("Deadline")
                if not isinstance(deadline, (int, float)):
                    continue
                record_id = task["record_id"]

                kind = None
                if deadline <= h2_ms and deadline > now_ms:
                    kind = "2h"
                elif deadline <= h24_ms and deadline > now_ms:
                    kind = "24h"
                if not kind:
                    continue

                notifs = await db.get_unnotified_tasks(db._db, boss["chat_id"], kind)
                notif = next((n for n in notifs if n["task_record_id"] == record_id), None)
                if not notif:
                    continue

                # Find person row for the assignee so _resolve_task_targets can
                # decide group vs DM. People not in Lark → person=None → fallback
                # to the task's Group ID if any.
                people = await lark.search_records(boss["lark_base_token"], boss["lark_table_people"])
                assignee_name = task.get("Assignee", "").lower()
                person = next(
                    (p for p in people if assignee_name in (p.get("Tên", "") or "").lower()),
                    None,
                )
                primary, fallback = await _resolve_task_targets(task, person, boss["chat_id"])
                # If task was created from DM and assignee is unknown, the legacy
                # notif row may carry a pre-resolved chat id — keep it as a last
                # resort to preserve old behaviour.
                if not primary and not fallback:
                    primary = notif.get("assignee_chat_id")

                if primary or fallback:
                    label = "2 tiếng" if kind == "2h" else "24 tiếng"
                    msg = (
                        f"⏰ Task '{task.get('Tên task')}' còn khoảng {label} đến deadline!\n"
                        f"Hãy cập nhật tiến độ nhé."
                    )
                    if primary:
                        await telegram.send(primary, msg)
                    if fallback:
                        await telegram.send(fallback, msg)
                await db.mark_notification_sent(db._db, record_id, boss["chat_id"], kind)
        except Exception:
            logger.exception("[scheduler] Deadline push failed for %s", boss.get("name"))


async def _after_deadline_check():
    """Every 30min: DM assignees of overdue tasks, report to boss."""
    from datetime import datetime, timezone

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    bosses = await db.get_all_bosses()

    for boss in bosses:
        try:
            tasks = await lark.search_records(boss["lark_base_token"], boss["lark_table_tasks"])
            open_status = ("Mới", "Đang làm")
            overdue = [
                t for t in tasks
                if t.get("Status") in open_status
                and isinstance(t.get("Deadline"), (int, float))
                and t["Deadline"] < now_ms
            ]
            if not overdue:
                continue

            unnotified = await db.get_unnotified_overdue_tasks(db._db, str(boss["chat_id"]))
            unnotified_ids = {n["task_record_id"] for n in unnotified}

            report_lines = []
            for task in overdue:
                record_id = task["record_id"]
                if record_id not in unnotified_ids:
                    continue

                assignee_name = task.get("Assignee", "")
                people = await lark.search_records(boss["lark_base_token"], boss["lark_table_people"])
                person = next(
                    (p for p in people if assignee_name.lower() in p.get("Tên", "").lower()),
                    None,
                )
                primary, fallback = await _resolve_task_targets(task, person, boss["chat_id"])
                task_name = task.get("Tên task", "?")
                msg = (
                    f"Task '{task_name}' đã quá hạn rồi!\n"
                    f"Bạn có thể update tiến độ cho {boss['name']} biết không?"
                )
                if primary:
                    await telegram.send(primary, msg)
                    await db.log_outbound_dm(
                        boss_chat_id=boss["chat_id"],
                        to_chat_id=primary,
                        to_name=assignee_name,
                        content=msg,
                        trigger_type="deadline_push",
                        task_id=record_id,
                    )
                if fallback:
                    await telegram.send(fallback, msg)
                if primary:
                    report_lines.append(f"Đã nhắc {assignee_name}: '{task_name}'")
                else:
                    report_lines.append(
                        f"'{task_name}' — {assignee_name} chưa có Chat ID và task không từ group"
                    )

                await db.mark_overdue_notified(db._db, record_id, str(boss["chat_id"]))

            if report_lines:
                await telegram.send(
                    boss["chat_id"],
                    "Báo cáo task quá hạn:\n" + "\n".join(report_lines),
                )
        except Exception:
            logger.exception("[scheduler] _after_deadline_check failed for %s", boss.get("name"))


def _coerce_lark_status(raw) -> str | None:
    """Normalise Lark's `Trạng thái` field across shapes.

    Bitable can return single-select / text values as raw str, wrapped
    {"text": "..."}, or list-of-{"text": ...}. The naive `rec.get(...)`
    used to demote any non-str shape to "pending", which (after the
    fire-path pushed "done" to Lark) caused the reverse-sync guard to
    re-heal Lark every 30s in a tight no-op loop.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        s = raw.strip().lower()
        return s if s in ("pending", "done") else None
    if isinstance(raw, list) and raw:
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("value") or item.get("name") or ""))
            else:
                parts.append(str(item))
        return _coerce_lark_status("".join(parts))
    if isinstance(raw, dict):
        return _coerce_lark_status(raw.get("text") or raw.get("value") or raw.get("name"))
    return None


def _coerce_sqlite_id(raw) -> int | None:
    """Parse Lark's 'SQLite ID' field across all shapes it can come back as.

    Bitable returns number fields as int/float, but text-shaped or rich-text
    columns come back as str / list-of-{'text': ...}. A narrow isinstance
    check used to drop those cases, which caused the reverse-sync to think
    the Lark record was unlinked and create a duplicate SQLite row every 30s.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        v = int(raw)
        return v if v > 0 else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            v = int(float(s))
            return v if v > 0 else None
        except ValueError:
            return None
    if isinstance(raw, list) and raw:
        # Lark rich text: [{"text": "5", "type": "text"}, ...]
        parts = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return _coerce_sqlite_id("".join(parts))
    if isinstance(raw, dict):
        return _coerce_sqlite_id(raw.get("text") or raw.get("value"))
    return None


async def _sync_lark_to_sqlite():
    """Lark → SQLite reverse-sync.

    Reminders block runs every call (every 30s). Tasks status sync + Notes block
    run only on the every-5-min gate.
    """
    bosses = await db.get_all_bosses()
    now = datetime.utcnow()
    do_full_sync = (now.minute % 5 == 0 and now.second < 35)
    settings_tz = ZoneInfo(_settings.timezone) if _settings else ZoneInfo("Asia/Ho_Chi_Minh")

    for boss in bosses:
        try:
            await _reverse_sync_reminders_for_boss(boss, settings_tz)
        except Exception:
            logger.exception("[scheduler] reminder reverse-sync failed for %s", boss.get("name"))

        if not do_full_sync:
            continue

        # Task terminal-state sync (existing behaviour)
        task_tbl = boss.get("lark_table_tasks", "")
        if task_tbl:
            try:
                tasks = await lark.search_records(boss["lark_base_token"], task_tbl)
                for t in tasks:
                    record_id = t.get("record_id")
                    status = t.get("Status", "")
                    if status in ("Hoàn thành", "Huỷ", "Done", "Cancelled") and record_id:
                        await db._db.execute(
                            """UPDATE task_notifications SET notified_overdue=1
                               WHERE task_record_id=? AND boss_chat_id=?""",
                            (record_id, str(boss["chat_id"])),
                        )
                await db._db.commit()
            except Exception:
                logger.exception("[scheduler] task terminal sync failed for %s", boss.get("name"))

        try:
            await _reverse_sync_notes_for_boss(boss)
        except Exception:
            logger.exception("[scheduler] notes reverse-sync failed for %s", boss.get("name"))


async def _reverse_sync_reminders_for_boss(boss: dict, settings_tz: ZoneInfo) -> None:
    from src.repositories.reminder_repo import ReminderRepo

    tbl = boss.get("lark_table_reminders", "")
    if not tbl:
        return

    repo = ReminderRepo(db._db)
    boss_chat_id = str(boss["chat_id"])
    base = boss["lark_base_token"]
    records = await lark.search_records(base, tbl)

    seen_lark_ids: set[str] = set()
    for rec in records:
        rec_id = rec.get("record_id", "")
        if rec_id:
            seen_lark_ids.add(rec_id)
        sqlite_id = _coerce_sqlite_id(rec.get("SQLite ID"))
        linked_row: dict | None = None

        # Defensive: even if SQLite ID didn't decode, we may already have a
        # SQLite row linked by lark_record_id from a prior sync. Use that to
        # avoid creating a duplicate (the loop bug).
        if sqlite_id is None and rec_id:
            linked_row = await repo.find_by_lark_id(boss_chat_id, rec_id)
            if linked_row:
                sqlite_id = int(linked_row["id"])

        if sqlite_id is not None and sqlite_id > 0:
            new_content = rec.get("Nội dung", "")
            new_status = _coerce_lark_status(rec.get("Trạng thái")) or "pending"
            remind_at_str = rec.get("Thời gian nhắc", "")
            remind_at_dt = None
            if remind_at_str:
                try:
                    naive = datetime.strptime(remind_at_str, "%Y-%m-%d %H:%M")
                    remind_at_dt = naive.replace(tzinfo=settings_tz).astimezone(
                        ZoneInfo("UTC")
                    ).replace(tzinfo=None)
                except (ValueError, TypeError):
                    logger.warning(
                        "[scheduler] bad time '%s' on lark reminder %s",
                        remind_at_str, rec_id,
                    )
            # Status is monotonic: pending → done only. If SQLite already says
            # 'done' (we fired it), never let a stale Lark 'pending' demote it
            # — that demotion is what made reminders re-fire every minute.
            # Instead push the truth (done) back to Lark.
            current = linked_row or await repo.get_by_id(sqlite_id)
            current_status = (current or {}).get("status")
            status_to_write: str | None = new_status
            if current_status == "done" and new_status == "pending":
                status_to_write = None  # don't downgrade
                if rec_id:
                    try:
                        await lark.with_retry(lambda: lark.update_record(
                            base, tbl, rec_id, {"Trạng thái": "done"},
                        ))
                    except Exception:
                        logger.warning(
                            "[scheduler] could not heal Lark Trạng thái=done for %s",
                            rec_id, exc_info=True,
                        )
            await repo.update_remind_at_and_content(
                sqlite_id, content=new_content, remind_at=remind_at_dt,
                status=status_to_write,
            )
            # Self-heal: if Lark has no SQLite ID set, patch it in-place so
            # the next sync takes the fast path. Direct update_record only —
            # never sync_reminder_to_lark here (it'd create a duplicate).
            if rec_id and _coerce_sqlite_id(rec.get("SQLite ID")) is None:
                try:
                    await lark.with_retry(lambda: lark.update_record(
                        base, tbl, rec_id, {"SQLite ID": sqlite_id},
                    ))
                except Exception:
                    logger.warning(
                        "[scheduler] could not patch SQLite ID on lark %s",
                        rec_id, exc_info=True,
                    )
            continue

        # Genuine manual-add in Lark (no SQLite ID, no prior link).
        remind_at_str = rec.get("Thời gian nhắc", "")
        try:
            naive = datetime.strptime(remind_at_str, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            logger.warning(
                "[scheduler] cannot parse time on manual-add lark reminder %s: %r",
                rec_id, remind_at_str,
            )
            continue
        remind_dt = naive.replace(tzinfo=settings_tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        new_id = await db.create_reminder(
            boss_chat_id=boss_chat_id,
            content=rec.get("Nội dung", ""),
            remind_at=remind_dt,
            target_chat_id=None,
            target_name=rec.get("Người nhận", "") or "",
        )
        if rec_id:
            await repo.set_lark_record_id(new_id, rec_id)
            # Write SQLite ID back to the SAME Lark record. Must use
            # update_record directly — sync_reminder_to_lark searches by
            # SQLite ID, won't find it (we just minted it), and falls
            # through to creating ANOTHER Lark record, which is exactly
            # the duplication loop we're fixing.
            try:
                await lark.with_retry(lambda: lark.update_record(
                    base, tbl, rec_id, {"SQLite ID": new_id},
                ))
            except Exception:
                logger.warning(
                    "[scheduler] could not write SQLite ID back to lark %s",
                    rec_id, exc_info=True,
                )

    # Tombstone vanished
    for row in await repo.list_with_lark_id(boss_chat_id):
        if row["lark_record_id"] not in seen_lark_ids and row["status"] == "pending":
            await repo.tombstone(row["id"])

    # Reconcile push for DB rows lacking lark_record_id
    for row in await repo.list_unsynced_pending(boss_chat_id):
        try:
            remind_local = row["remind_at"]
            try:
                dt_utc = datetime.fromisoformat(remind_local.strip()).replace(tzinfo=ZoneInfo("UTC"))
                remind_local_str = dt_utc.astimezone(settings_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                remind_local_str = remind_local
            rec_id = await lark.with_retry(lambda r=row, rl=remind_local_str: lark.sync_reminder_to_lark(
                base, tbl,
                {
                    "content": r["content"],
                    "remind_at_local": rl,
                    "target_name": r.get("target_name") or "",
                    "status": r["status"],
                },
                r["id"],
            ))
            if rec_id:
                await repo.set_lark_record_id(row["id"], rec_id)
        except Exception:
            logger.warning(
                "[scheduler] reconcile push failed for reminder %d", row["id"],
                exc_info=True,
            )


async def _reverse_sync_notes_for_boss(boss: dict) -> None:
    from src.repositories.note_repo import NoteRepo

    tbl = boss.get("lark_table_notes", "")
    if not tbl:
        return

    repo = NoteRepo(db._db)
    boss_chat_id = str(boss["chat_id"])
    base = boss["lark_base_token"]
    records = await lark.search_records(base, tbl)

    seen_lark_ids: set[str] = set()
    for rec in records:
        rec_id = rec.get("record_id", "")
        if rec_id:
            seen_lark_ids.add(rec_id)
        note_type = rec.get("Loại", "")
        ref_id = str(rec.get("Ref ID", "") or "")
        content = rec.get("Nội dung", "")
        if not note_type or not ref_id:
            continue
        sqlite_id_raw = rec.get("SQLite ID")

        if isinstance(sqlite_id_raw, (int, float)) and int(sqlite_id_raw) > 0:
            sqlite_id = int(sqlite_id_raw)
            existing = await repo.get_by_id(sqlite_id)
            if existing and existing.get("content") != content:
                await repo.update_content_by_id(sqlite_id, content)
        else:
            new_id = await repo.upsert(boss_chat_id, note_type, ref_id, content)
            if rec_id:
                await repo.set_lark_record_id(new_id, rec_id)
            try:
                await lark.with_retry(lambda nid=new_id, c=content, nt=note_type, r=ref_id:
                    lark.sync_note_to_lark(
                        base, tbl,
                        {
                            "type": nt, "ref_id": r,
                            "content": c,
                            "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
                        },
                        nid,
                    ))
            except Exception:
                logger.warning(
                    "[scheduler] could not write SQLite ID back for note %s", rec_id,
                    exc_info=True,
                )

    # Delete vanished
    for row in await repo.list_with_lark_id(boss_chat_id):
        if row["lark_record_id"] not in seen_lark_ids:
            await repo.delete_by_id(row["id"])

    # Reconcile push
    for row in await repo.list_unsynced(boss_chat_id):
        try:
            rec_id = await lark.with_retry(lambda r=row: lark.sync_note_to_lark(
                base, tbl,
                {
                    "type": r["type"], "ref_id": r["ref_id"],
                    "content": r["content"],
                    "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
                },
                r["id"],
            ))
            if rec_id:
                await repo.set_lark_record_id(row["id"], rec_id)
        except Exception:
            logger.warning(
                "[scheduler] reconcile push failed for note %d", row["id"],
                exc_info=True,
            )


async def _run_dynamic_reviews():
    """Moi phut: chay scheduled_reviews dong theo DB thay vi hardcode."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from src.advisor import run_daily_review
    from src.services.summary_service import get_summary

    reviews = await db.get_all_enabled_reviews(db._db)
    bosses_cache: dict = {}

    for review in reviews:
        try:
            tz = ZoneInfo(review.get("timezone", "Asia/Ho_Chi_Minh"))
            current_time = datetime.now(tz).strftime("%H:%M")
            if current_time != review["cron_time"]:
                continue

            owner_id = review["owner_id"]
            if owner_id not in bosses_cache:
                bosses_cache[owner_id] = await db.get_boss(owner_id)
            boss = bosses_cache[owner_id]
            if not boss:
                continue

            ctx = _make_ctx(boss)
            content_type = review["content_type"]

            if content_type == "morning_brief":
                text = await run_daily_review(ctx, _settings)
            elif content_type == "evening_summary":
                text = await get_summary(ctx, "today")
                text = f"*Tổng kết cuối ngày:*\n\n{text}"
            elif content_type == "custom":
                prompt = review.get("custom_prompt", "")
                if not prompt:
                    continue
                text = await run_daily_review(ctx, _settings, custom_prompt=prompt)
            elif content_type == "group_brief":
                from src.agent.llm_for_ctx import get_llm_for_ctx  # noqa: PLC0415
                _oai = await get_llm_for_ctx(ctx)
                tasks_data = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
                tasks_text = "\n".join(
                    f"- {t.get('Tên task', '?')} | {t.get('Assignee', '?')} | deadline: {t.get('Deadline', '?')} | status: {t.get('Status', '?')}"
                    for t in tasks_data
                ) or "(không có task)"
                response, _ = await _oai.chat_with_tools(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Tạo briefing ngắn gọn cho nhóm (không phải cho sếp):\n"
                                "1. Deadline hôm nay của team\n"
                                "2. Ai đang có nhiều task nhất\n"
                                "3. Task mới được giao từ hôm qua\n"
                                "Tone tự nhiên, như thông báo nội bộ."
                            ),
                        },
                        {"role": "user", "content": f"Danh sách task:\n{tasks_text}"},
                    ],
                    [],
                )
                text = response.content or "Không thể tạo briefing."
            else:
                continue

            # Route: group chat or boss DM. Both ids are internal UUIDs.
            target_chat_id = review.get("group_chat_id") or owner_id

            # Build group context if sending to a group
            group_context_str = ""
            if review.get("group_chat_id"):
                try:
                    from src.context_builder import build_group_context as _bgc  # noqa: PLC0415
                    grp = await _bgc(review["group_chat_id"], owner_id)
                    if grp:
                        group_context_str = (
                            f"\nNhóm: {grp.get('group_name', '')} | "
                            f"Đang bàn: {grp.get('active_topic', '')} | "
                            f"Ghi chú: {grp.get('group_note', '')}"
                        )
                except Exception:
                    pass

            if group_context_str and text:
                text = group_context_str + "\n\n" + text

            await telegram.send(target_chat_id, text)
            logger.info("[scheduler] Dynamic review '%s' sent to %s", content_type, boss["name"])
        except Exception:
            logger.exception("[scheduler] Dynamic review failed for review_id=%s", review.get("id"))


async def _seed_default_reviews():
    """One-time seed: add default morning/evening reviews for bosses without any review config."""
    bosses = await db.get_all_bosses()
    for boss in bosses:
        existing = await db.list_scheduled_reviews(db._db, str(boss["chat_id"]))
        if not existing:
            await db.create_scheduled_review(db._db, str(boss["chat_id"]), "08:00", "morning_brief")
            await db.create_scheduled_review(db._db, str(boss["chat_id"]), "17:00", "evening_summary")
            logger.info("[scheduler] Seeded default reviews for %s", boss["name"])


async def start(settings: Settings):
    global _scheduler, _settings
    _settings = settings
    _scheduler = AsyncIOScheduler()

    # Seed default reviews for existing bosses (idempotent)
    try:
        await _seed_default_reviews()
    except Exception:
        logger.exception("[scheduler] Failed to seed default reviews")

    # Dynamic reviews replace hardcoded morning/evening jobs
    _scheduler.add_job(_run_dynamic_reviews, IntervalTrigger(minutes=1))

    # Fixed jobs
    _scheduler.add_job(_check_deadlines, CronTrigger(hour=9, minute=30,
                                                      timezone=settings.timezone))
    _scheduler.add_job(_check_reminders, IntervalTrigger(minutes=1))
    _scheduler.add_job(_check_deadline_push, IntervalTrigger(minutes=30))
    _scheduler.add_job(_after_deadline_check, IntervalTrigger(minutes=30))
    _scheduler.add_job(_check_no_reply_reminders, IntervalTrigger(minutes=30))
    _scheduler.add_job(_sync_lark_to_sqlite, IntervalTrigger(seconds=30))
    _scheduler.start()
    logger.info("Scheduler started")


async def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)

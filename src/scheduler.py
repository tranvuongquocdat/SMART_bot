"""
Scheduler: morning review, evening summary, deadline alerts, reminders.
Loops through all bosses for each scheduled job.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.config import Settings
from src.context import ChatContext
from src.services import lark, telegram

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
    from src.tools.summary import get_summary
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            text = await get_summary(ctx, "today")
            await telegram.send(boss["chat_id"], f"*Tong ket cuoi ngay:*\n\n{text}")
        except Exception:
            logger.exception("[scheduler] Evening summary failed for %s", boss["name"])


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

                # Deadline tomorrow -> nhac assignee
                if tomorrow_ms <= dl < tomorrow_end and person:
                    target_id = person.get("Chat ID")
                    if target_id:
                        await telegram.send(
                            int(target_id),
                            f"Nhac nho: Task '{r.get('Tên task', '?')}' deadline ngay mai!"
                        )

                # Overdue -> nhac assignee + bao boss
                if dl < today_ms:
                    if person and person.get("Chat ID"):
                        await telegram.send(
                            int(person["Chat ID"]),
                            f"Task '{r.get('Tên task', '?')}' da QUA HAN! Cap nhat tien do nhe."
                        )
                    await telegram.send(
                        boss["chat_id"],
                        f"Task qua han: '{r.get('Tên task', '?')}' ({r.get('Assignee', 'N/A')})"
                    )
        except Exception:
            logger.exception("[scheduler] Deadline check failed for %s", boss["name"])


async def _check_reminders():
    """Moi phut: check reminders den gio -> qua agent LLM de gui loi nhac tu nhien."""
    from src import agent  # noqa: PLC0415

    reminders = await db.get_due_reminders()
    for r in reminders:
        try:
            await agent.send_reminder(r, _settings)
            await db.mark_reminder_done(r["id"])
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

                assignee_chat_id = notif.get("assignee_chat_id")
                if assignee_chat_id:
                    label = "2 tiếng" if kind == "2h" else "24 tiếng"
                    await telegram.send(
                        int(assignee_chat_id),
                        f"⏰ Task '{task.get('Tên task')}' còn khoảng {label} đến deadline!\n"
                        f"Hãy cập nhật tiến độ nhé.",
                    )
                await db.mark_notification_sent(db._db, record_id, boss["chat_id"], kind)
        except Exception:
            logger.exception("[scheduler] Deadline push failed for %s", boss.get("name"))


async def _sync_lark_to_sqlite():
    """Moi 30s: sync Lark Reminders table -> SQLite (2-way sync)."""
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            tbl = boss.get("lark_table_reminders", "")
            if not tbl:
                continue
            records = await lark.search_records(boss["lark_base_token"], tbl)
            for rec in records:
                sqlite_id = rec.get("SQLite ID")
                if not isinstance(sqlite_id, (int, float)):
                    continue
                await db.sync_reminder_from_lark(
                    db._db,
                    int(sqlite_id),
                    content=rec.get("Nội dung", ""),
                    status=rec.get("Trạng thái", "pending"),
                )
        except Exception:
            logger.exception("[scheduler] Lark sync failed for %s", boss.get("name"))


async def _run_dynamic_reviews():
    """Moi phut: chay scheduled_reviews dong theo DB thay vi hardcode."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from src.advisor import run_daily_review
    from src.tools.summary import get_summary

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
                from src.services import openai_client as _oai  # noqa: PLC0415
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

            # Route: group chat or boss DM
            target_chat_id = review.get("group_chat_id") or int(owner_id)
            await telegram.send(int(target_chat_id), text)
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
    _scheduler.add_job(_sync_lark_to_sqlite, IntervalTrigger(seconds=30))
    _scheduler.start()
    logger.info("Scheduler started")


async def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)

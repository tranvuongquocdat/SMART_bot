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


async def start(settings: Settings):
    global _scheduler, _settings
    _settings = settings
    tz = settings.timezone
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_morning_review, CronTrigger(hour=8, timezone=tz))
    _scheduler.add_job(_evening_summary, CronTrigger(hour=17, timezone=tz))
    _scheduler.add_job(_check_deadlines, CronTrigger(hour=9, minute=30, timezone=tz))
    _scheduler.add_job(_check_reminders, IntervalTrigger(minutes=1))
    _scheduler.start()
    logger.info("Scheduler started")


async def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)

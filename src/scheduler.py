from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src import db
from src.services import lark, telegram
from src.config import Settings

_scheduler: AsyncIOScheduler | None = None
_settings: Settings | None = None


async def _send_to_all(text: str):
    chat_ids = await db.get_all_chat_ids()
    for chat_id in chat_ids:
        await telegram.send(chat_id, text)


async def _morning_summary():
    from src.tools.summary import get_summary

    text = await get_summary("today")
    await _send_to_all(f"*Chào buổi sáng!*\n\n{text}")


async def _evening_summary():
    from src.tools.summary import get_summary

    text = await get_summary("today")
    await _send_to_all(f"*Tóm tắt cuối ngày:*\n\n{text}")


async def _check_deadlines():
    from datetime import date, timedelta

    records = await lark.search_records(_settings.lark_table_tasks)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    due_soon = [
        r for r in records
        if r.get("Trạng thái") in ("Mới", "Đang làm")
        and r.get("Deadline") == tomorrow
    ]

    if due_soon:
        lines = ["*Nhắc deadline ngày mai:*"]
        for r in due_soon:
            lines.append(f"  - {r.get('Tên task', '?')} | {r.get('Khách hàng', 'N/A')}")
        await _send_to_all("\n".join(lines))


async def start(settings: Settings):
    global _scheduler, _settings
    _settings = settings
    tz = settings.timezone
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_morning_summary, CronTrigger(hour=8, timezone=tz))
    _scheduler.add_job(_evening_summary, CronTrigger(hour=17, timezone=tz))
    _scheduler.add_job(_check_deadlines, CronTrigger(hour=20, timezone=tz))
    _scheduler.start()


async def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)

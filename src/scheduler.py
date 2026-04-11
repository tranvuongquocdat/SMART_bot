from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.services import lark, telegram
from src.config import Settings

_scheduler: AsyncIOScheduler | None = None
_settings: Settings | None = None


async def _morning_summary():
    from src.tools.summary import get_summary

    text = await get_summary("today")
    await telegram.send(_settings.ceo_chat_id, f"*Chào buổi sáng!*\n\n{text}")


async def _evening_summary():
    from src.tools.summary import get_summary

    text = await get_summary("today")
    await telegram.send(_settings.ceo_chat_id, f"*Tóm tắt cuối ngày:*\n\n{text}")


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
        await telegram.send(_settings.ceo_chat_id, "\n".join(lines))


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

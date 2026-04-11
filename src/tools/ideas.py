from datetime import date

from src.services import lark
from src.config import Settings

_settings: Settings | None = None


def init(settings: Settings):
    global _settings
    _settings = settings


async def create_idea(content: str, tags: str = "") -> str:
    fields = {
        "Nội dung": content,
        "Ngày tạo": date.today().isoformat(),
    }
    if tags:
        fields["Tag"] = tags

    await lark.create_record(_settings.lark_table_ideas, fields)
    return f"Đã lưu ý tưởng: {content}"

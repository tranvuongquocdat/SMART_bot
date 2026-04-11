from src import db


async def update_personal_note(note_content: str) -> str:
    await db.update_personal_note(note_content)
    return "Đã cập nhật personal note."

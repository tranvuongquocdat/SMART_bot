from src import db


async def update_personal_note(note_content: str, chat_id: int) -> str:
    await db.update_personal_note(chat_id, note_content)
    return "Đã cập nhật personal note."

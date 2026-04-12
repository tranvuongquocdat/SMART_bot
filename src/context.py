"""
Context resolver: từ tin nhắn đến → xác định ai, thuộc sếp nào, quyền gì.
"""
from dataclasses import dataclass
from src import db


@dataclass
class ChatContext:
    # Ai gửi
    sender_chat_id: int
    sender_name: str
    sender_type: str  # boss / member / partner / unknown

    # Thuộc workspace nào
    boss_chat_id: int | None
    boss_name: str

    # Lark Base
    lark_base_token: str
    lark_table_people: str
    lark_table_tasks: str
    lark_table_projects: str
    lark_table_ideas: str

    # Chat info
    chat_id: int  # conversation chat_id (có thể là group)
    is_group: bool
    group_name: str

    # Qdrant collections
    messages_collection: str
    tasks_collection: str


async def resolve(chat_id: int, sender_id: int, is_group: bool) -> ChatContext | None:
    """
    Resolve context từ tin nhắn đến.
    Returns None nếu người gửi chưa onboard (unknown).
    """
    boss = None
    boss_chat_id = None
    sender_type = "unknown"
    sender_name = ""
    group_name = ""

    if is_group:
        group = await db.get_group(chat_id)
        if not group:
            return None
        boss_chat_id = group["boss_chat_id"]
        group_name = group["group_name"]

        person = await db.get_person(sender_id)
        if person:
            sender_type = person["type"]
            sender_name = person["name"]
    else:
        # Chat 1-1: sender_id == chat_id
        boss_data = await db.get_boss(sender_id)
        if boss_data:
            boss = boss_data
            sender_type = "boss"
            sender_name = boss_data["name"]
            boss_chat_id = sender_id
        else:
            person = await db.get_person(sender_id)
            if person:
                sender_type = person["type"]
                sender_name = person["name"]
                boss_chat_id = person["boss_chat_id"]
            else:
                return None

    if not boss:
        boss = await db.get_boss(boss_chat_id)
        if not boss:
            return None

    return ChatContext(
        sender_chat_id=sender_id,
        sender_name=sender_name,
        sender_type=sender_type,
        boss_chat_id=boss["chat_id"],
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        chat_id=chat_id,
        is_group=is_group,
        group_name=group_name,
        messages_collection=f"messages_{boss['chat_id']}",
        tasks_collection=f"tasks_{boss['chat_id']}",
    )

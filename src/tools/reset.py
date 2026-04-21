"""
reset.py — Nuclear workspace reset.
3-step: initiate → confirm company name → confirm phrase → execute.
State stored in SQLite sessions table (not in-memory).
"""
import asyncio
import json
import logging

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.reset")

SEPARATOR = (
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "       WORKSPACE RESET\n"
    "  Old data has been deleted.\n"
    "  New session starts here.\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━"
)


async def initiate_reset(ctx: ChatContext) -> str:
    """Step 1: Start reset flow. Ask boss to type company name in UPPERCASE."""
    boss = await db.get_boss(ctx.boss_chat_id)
    company = boss.get("company", str(ctx.boss_chat_id)) if boss else str(ctx.boss_chat_id)
    upper = company.upper()

    await db.set_session(
        ctx.boss_chat_id,
        "reset_step",
        json.dumps({"step": 1, "company": company}),
        ttl_minutes=10,
    )

    return (
        f"⚠️ You are about to DELETE ALL DATA for workspace *{company}*.\n"
        f"This removes Lark Base, all SQLite records, chat history, and Qdrant data.\n\n"
        f"To confirm, type the company name in UPPERCASE:\n`{upper}`"
    )


async def confirm_reset_step1(ctx: ChatContext, user_input: str) -> str:
    """Step 2: Validate company name. If match, ask for final confirmation phrase."""
    raw = await db.get_session(ctx.boss_chat_id, "reset_step")
    if not raw:
        return "No active reset flow. Say 'reset workspace' to start."

    session = json.loads(raw)
    if session.get("step") != 1:
        return "Unexpected reset state. Say 'reset workspace' to restart."

    expected = session["company"].upper()
    if user_input.strip() != expected:
        await db.delete_session(ctx.boss_chat_id, "reset_step")
        return f"Name did not match. Reset cancelled."

    await db.set_session(
        ctx.boss_chat_id,
        "reset_step",
        json.dumps({"step": 2, "company": session["company"]}),
        ttl_minutes=5,
    )
    return "Type `tôi chắc chắn` (or `i am sure`) to execute the reset."


async def execute_reset(ctx: ChatContext, confirmation: str) -> str:
    """Step 3: Final confirmation. Execute nuclear reset."""
    raw = await db.get_session(ctx.boss_chat_id, "reset_step")
    if not raw:
        return "No active reset flow."

    session = json.loads(raw)
    if session.get("step") != 2:
        return "Unexpected reset state. Say 'reset workspace' to restart."

    if confirmation.strip().lower() not in ("tôi chắc chắn", "i am sure"):
        await db.delete_session(ctx.boss_chat_id, "reset_step")
        return "Confirmation phrase did not match. Reset cancelled."

    await db.delete_session(ctx.boss_chat_id, "reset_step")
    return await _do_reset(ctx)


async def _do_reset(ctx: ChatContext) -> str:
    boss_id = ctx.boss_chat_id
    boss = await db.get_boss(boss_id)
    if not boss:
        return "Workspace not found."

    _db = await db.get_db()

    # Step 0: Capture member IDs BEFORE any deletion
    async with _db.execute(
        "SELECT chat_id FROM memberships WHERE boss_chat_id = ?",
        (str(boss_id),),
    ) as cur:
        member_rows = await cur.fetchall()
    member_ids = [int(r["chat_id"]) for r in member_rows]

    # Step 1: Notify members
    company = boss.get("company", str(boss_id))
    for mid in member_ids:
        if mid != boss_id:
            try:
                await telegram.send(mid, f"The workspace '{company}' has been reset by the boss.")
            except Exception:
                pass

    # Step 2: Delete Lark Base (fallback: clear all records if delete API fails)
    base_token = boss.get("lark_base_token", "")
    if base_token:
        try:
            await lark.delete_base(base_token)
            logger.info("[reset] Lark base %s moved to trash for boss %s", base_token, boss_id)
        except Exception:
            logger.exception("[reset] delete_base failed, falling back to per-record cleanup")
            await _delete_all_lark_records(boss, base_token)

    # Step 3-9: Delete SQLite rows (correct order — bosses row last)
    all_chat_ids = list({boss_id} | {m for m in member_ids})
    placeholders = ",".join("?" * len(all_chat_ids))

    for sql, params in [
        ("DELETE FROM notes WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM reminders WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM scheduled_reviews WHERE owner_id = ?", (str(boss_id),)),
        ("DELETE FROM pending_approvals WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM task_notifications WHERE boss_chat_id = ?", (str(boss_id),)),
        (f"DELETE FROM messages WHERE chat_id IN ({placeholders})", all_chat_ids),
        ("DELETE FROM people_map WHERE boss_chat_id = ?", (str(boss_id),)),
        ("UPDATE memberships SET status = 'workspace_reset' WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM bosses WHERE chat_id = ?", (boss_id,)),
    ]:
        try:
            await _db.execute(sql, params)
        except Exception:
            logger.exception("Failed to execute: %s", sql)
    await _db.commit()

    # Step 10: Delete Qdrant collections
    # qdrant.py exposes no delete_collection helper — call the underlying client directly.
    try:
        from src.services import qdrant as _qdrant_mod
        client = _qdrant_mod._qdrant
        if client is not None:
            await asyncio.gather(
                client.delete_collection(f"messages_{boss_id}"),
                client.delete_collection(f"tasks_{boss_id}"),
                return_exceptions=True,
            )
    except Exception:
        logger.exception("Failed to delete Qdrant collections for boss %s", boss_id)

    # Step 11: Send separator
    try:
        await telegram.send(boss_id, SEPARATOR)
    except Exception:
        pass

    return "Reset complete. Send any message to start over."


async def _delete_all_lark_records(boss: dict, base_token: str) -> None:
    """Fallback: delete all records per table when delete_base not available."""
    from src.services import lark as _lark
    table_ids = [
        boss.get("lark_table_people", ""),
        boss.get("lark_table_tasks", ""),
        boss.get("lark_table_projects", ""),
        boss.get("lark_table_ideas", ""),
        boss.get("lark_table_reminders", ""),
        boss.get("lark_table_notes", ""),
    ]
    for table_id in table_ids:
        if not table_id:
            continue
        try:
            records = await _lark.search_records(base_token, table_id)
            await asyncio.gather(
                *(_lark.delete_record(base_token, table_id, r["record_id"]) for r in records),
                return_exceptions=True,
            )
        except Exception:
            logger.exception("Failed to delete records from table %s", table_id)

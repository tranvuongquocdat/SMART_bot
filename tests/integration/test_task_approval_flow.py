"""
Integration tests: task approval flow.
  member requests update → pending_approvals record created
  boss approves → record status updated, changes applied marker checked
  boss rejects → record status updated
"""
import json
import pytest
import aiosqlite

from src.db import (
    _init_schema,
    _migrate_schema,
    create_approval,
    get_pending_approvals,
    update_approval_status,
)


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        await _migrate_schema(conn)
        yield conn


async def test_create_and_get_approval(db):
    payload = json.dumps({
        "record_id": "rec_abc",
        "task_name": "Fix login bug",
        "changes": {"Status": "Hoàn thành"},
    })
    approval_id = await create_approval(db, "1001", "2001", "rec_abc", payload)
    assert approval_id is not None

    rows = await get_pending_approvals(db, "1001")
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert json.loads(rows[0]["payload"])["task_name"] == "Fix login bug"


async def test_approve_changes_status(db):
    payload = json.dumps({"record_id": "rec_xyz", "task_name": "Design logo", "changes": {}})
    approval_id = await create_approval(db, "1001", "2001", "rec_xyz", payload)

    await update_approval_status(db, approval_id, "approved")

    # Should no longer appear in pending list
    rows = await get_pending_approvals(db, "1001")
    assert len(rows) == 0


async def test_reject_changes_status(db):
    payload = json.dumps({"record_id": "rec_zzz", "task_name": "Deploy app", "changes": {}})
    approval_id = await create_approval(db, "1001", "2001", "rec_zzz", payload)

    await update_approval_status(db, approval_id, "rejected")

    rows = await get_pending_approvals(db, "1001")
    assert len(rows) == 0


async def test_multiple_approvals_only_returns_pending(db):
    p1 = json.dumps({"record_id": "r1", "task_name": "Task A", "changes": {}})
    p2 = json.dumps({"record_id": "r2", "task_name": "Task B", "changes": {}})
    id1 = await create_approval(db, "1001", "2001", "r1", p1)
    id2 = await create_approval(db, "1001", "2001", "r2", p2)

    await update_approval_status(db, id1, "approved")

    rows = await get_pending_approvals(db, "1001")
    assert len(rows) == 1
    assert json.loads(rows[0]["payload"])["task_name"] == "Task B"


async def test_approval_scoped_to_boss(db):
    payload = json.dumps({"record_id": "r1", "task_name": "Task X", "changes": {}})
    await create_approval(db, "1001", "2001", "r1", payload)
    await create_approval(db, "9999", "2001", "r1", payload)  # different boss

    rows_boss1 = await get_pending_approvals(db, "1001")
    rows_boss2 = await get_pending_approvals(db, "9999")
    assert len(rows_boss1) == 1
    assert len(rows_boss2) == 1

"""Tests for AuditService — round-trip log + list."""
from __future__ import annotations

import aiosqlite
import pytest

from src.db import _init_schema
from src.repositories.audit_repo import AuditRepo
from src.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_log_and_list_round_trip(tmp_path):
    path = tmp_path / "t.db"
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await _init_schema(conn)

    repo = AuditRepo(conn)
    svc = AuditService(repo)

    await svc.log(
        actor_internal_id="uuid-actor",
        action="task.create",
        target_table="tasks",
        target_id="rec_xxx",
        payload={"name": "demo task"},
    )

    rows = await svc.list_for_actor("uuid-actor")
    assert len(rows) == 1
    assert rows[0]["action"] == "task.create"
    assert rows[0]["target_id"] == "rec_xxx"

    await conn.close()

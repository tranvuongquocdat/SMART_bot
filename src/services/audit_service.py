"""AuditService — append-only audit-trail facade.

Wired but not actively called this phase (Phase 4b services / Phase 7
admin layer light up the call sites). The shape is fixed now so future
callers don't refactor.
"""
from __future__ import annotations

from typing import Any, Optional

from src.repositories.audit_repo import AuditRepo


class AuditService:
    def __init__(self, audit_repo: AuditRepo) -> None:
        self._repo = audit_repo

    async def log(
        self,
        actor_internal_id: Optional[str],
        action: str,
        target_table: Optional[str] = None,
        target_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        """Append an audit-log row. Returns the new row id."""
        return await self._repo.log(
            actor_internal_id=actor_internal_id,
            action=action,
            target_table=target_table,
            target_id=target_id,
            payload=payload,
        )

    async def list_for_actor(
        self, actor_internal_id: str, limit: int = 50,
    ) -> list[dict]:
        return await self._repo.list_for_actor(actor_internal_id, limit)

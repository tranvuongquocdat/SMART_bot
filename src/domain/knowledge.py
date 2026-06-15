"""Domain types cho Knowledge/Memory core (Lớp 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class KnowledgeKind(str, Enum):
    DECISION = "decision"
    FACT = "fact"
    NOTE = "note"
    RISK = "risk"
    # Thêm kind mới = thêm member ở đây (kind là TEXT trong DB → KHÔNG cần migrate).


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"  # việc đã xong / rủi ro đã xử lý — GIỮ vết, vẫn tra được
    DELETED = "deleted"  # soft-delete; KHÔNG bao giờ xoá cứng


# Trạng thái còn "đáng tra cứu" (hiển thị trong search/recall). 'deleted' bị loại;
# 'resolved' vẫn giữ để trả lời "việc/rủi ro X đã xử lý chưa".
RETRIEVABLE_STATUSES = (KnowledgeStatus.ACTIVE.value, KnowledgeStatus.RESOLVED.value)


class RevisionOp(str, Enum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    RESOLVE = "resolve"  # đóng nhưng giữ vết (status=resolved)
    RESTORE = "restore"


class RevisionActor(str, Enum):
    EXTRACTOR = "extractor"
    DREAMING = "dreaming"
    BOSS = "boss"
    AGENT = "agent"


CANONICAL_KINDS = frozenset(k.value for k in KnowledgeKind)


@dataclass
class KnowledgeItem:
    id: int
    boss_id: int
    kind: str
    content: str
    status: str = KnowledgeStatus.ACTIVE.value
    title: str | None = None
    provider: str | None = None
    chat_id: str | None = None
    project_id: int | None = None
    importance: int | None = None
    confidence: float | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    # Task metadata (Pha B workload): item phân-công/cam-kết. assignee free-text;
    # status active=đang làm, resolved=đã xong. NULL = không phải task có chủ/hạn.
    assignee_name: str | None = None
    due_at: datetime | None = None
    qdrant_point_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

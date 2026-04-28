"""Enum validation helpers — pure, no I/O."""

# Canonical values — must match Lark field options exactly.
TASK_STATUS_VALUES: tuple[str, ...] = ("Mới", "Đang làm", "Hoàn thành", "Huỷ")
TASK_PRIORITY_VALUES: tuple[str, ...] = ("Cao", "Trung bình", "Thấp")


def validate_status(status: str) -> str:
    """Return the canonical status string, case-insensitive. Raises ValueError if unknown."""
    for v in TASK_STATUS_VALUES:
        if status.lower() == v.lower():
            return v
    raise ValueError(
        f"Status '{status}' không hợp lệ. Chỉ dùng: {', '.join(TASK_STATUS_VALUES)}"
    )


def validate_priority(priority: str) -> str:
    """Return the canonical priority string, case-insensitive. Raises ValueError if unknown."""
    for v in TASK_PRIORITY_VALUES:
        if priority.lower() == v.lower():
            return v
    raise ValueError(
        f"Priority '{priority}' không hợp lệ. Chỉ dùng: {', '.join(TASK_PRIORITY_VALUES)}"
    )

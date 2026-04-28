"""Pure date / time conversion helpers — no I/O, no state."""
from datetime import datetime


def date_to_ms(date_str: str) -> int:
    """Convert YYYY-MM-DD to millisecond timestamp (Lark uses ms)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def ms_to_date(ms: int) -> str:
    """Convert millisecond timestamp to YYYY-MM-DD string."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")

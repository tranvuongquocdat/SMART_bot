# Force-import core tool modules so their @tool decorators register on startup.
from src.tools.core import (  # noqa: F401
    action_items,
    memory,
    meta,
    notes,
    privacy,
    reminders,
    search,
    web,
)

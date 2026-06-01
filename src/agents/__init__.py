# Force-import operation modules so their @operation decorators register
# on process start. Modules are added per Batch D task as they land.
from src.agents import dm_responder, note_updater  # noqa: F401

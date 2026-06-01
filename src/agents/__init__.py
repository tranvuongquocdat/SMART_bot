# Force-import operation modules so their @operation decorators register
# on process start. Modules are added per Batch D task as they land.
from src.agents import (  # noqa: F401
    dm_responder,
    in_group_responder,
    note_updater,
)

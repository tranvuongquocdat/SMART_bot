"""JSONL command/event protocol between Python adapter and Node bridge.

Adapter writes one JSON command per line to bridge stdin:
    {"id": int, "method": str, "params": dict}

Bridge writes either a reply or an event per line to stdout:
    reply:  {"id": int, "result": dict}
            {"id": int, "error": {"code": str, "message": str}}
    event:  {"event": str, "data": dict}

Bridge stderr is free-form log forwarded to structlog at INFO/ERROR.

Methods (Python -> Bridge):
  - send           params={thread_id, text, thread_kind}
                   result={msg_id}
  - fetch_members  params={group_id}
                   result={member_ids: [str]}
  - get_own_id     params={}
                   result={own_id: str}
  - shutdown       params={}                  -> bridge exits 0

Events (Bridge -> Python):
  - ready          data={own_id}
  - message        data=<normalized inbound payload, see normalizer.py>
  - disconnected   data={reason, fatal}
  - status         data={status, reason}
"""

from __future__ import annotations

EVENT_READY = "ready"
EVENT_MESSAGE = "message"
EVENT_DISCONNECTED = "disconnected"
EVENT_STATUS = "status"

METHOD_SEND = "send"
METHOD_FETCH_MEMBERS = "fetch_members"
METHOD_GET_OWN_ID = "get_own_id"
METHOD_SHUTDOWN = "shutdown"


def make_command(req_id: int, method: str, params: dict) -> dict:
    return {"id": req_id, "method": method, "params": params}

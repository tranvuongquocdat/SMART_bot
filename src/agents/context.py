import contextvars
import dataclasses
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import structlog

from src.repositories.base import BossContext
from src.repositories.users import UsersRepo


@dataclass
class TraceCtx:
    trace_id: str
    span_id: str
    op_name: str
    boss_id: int


_current: contextvars.ContextVar[TraceCtx | None] = contextvars.ContextVar(
    "trace", default=None
)


@contextmanager
def trace_op(op_name: str, boss_id: int):
    """Bind a per-op trace context.

    Sets two scopes:
      1. ``_current`` ContextVar so callees (LLM gateway, tool dispatcher) can
         pull trace_id/span_id via ``current()``.
      2. structlog ``contextvars`` so every log line emitted under this scope
         carries trace_id / span_id / op / boss_id automatically.
    """
    tc = TraceCtx(
        trace_id=uuid.uuid4().hex,
        span_id=uuid.uuid4().hex,
        op_name=op_name,
        boss_id=boss_id,
    )
    tok = _current.set(tc)
    structlog.contextvars.bind_contextvars(
        trace_id=tc.trace_id,
        span_id=tc.span_id,
        op=op_name,
        boss_id=boss_id,
    )
    try:
        yield tc
    finally:
        _current.reset(tok)
        structlog.contextvars.unbind_contextvars(
            "trace_id", "span_id", "op", "boss_id"
        )


def current() -> TraceCtx | None:
    return _current.get()


async def build_context(deps_type, event, app_state):
    """Inspect deps_type dataclass fields; resolve from app_state + event."""
    boss_id = event["boss_id"]
    boss = await UsersRepo(
        app_state.db_pool, BossContext(boss_id, "boss")
    ).get_me()
    available = {
        "boss": boss,
        "memory": app_state.memory_provider,
        "retriever_factory": getattr(app_state, "retriever_factory", None),
        "llm": app_state.llm_gateway,
        "bus": app_state.bus,
        "db": app_state.db_pool,
        "qdrant": app_state.qdrant,
    }
    kwargs = {}
    for f in dataclasses.fields(deps_type):
        if f.name in available:
            kwargs[f.name] = available[f.name]
    return deps_type(**kwargs)

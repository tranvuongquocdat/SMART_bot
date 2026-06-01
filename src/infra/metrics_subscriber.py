"""Wire bus events → Prometheus counters.

Each handler is best-effort: a metric record failure must never break the
event pipeline (we just log + continue).
"""

from __future__ import annotations

import logging
import re

from src.infra.metrics import (
    messages_ingested,
    note_updates,
    op_fires,
    outbound,
)

log = logging.getLogger(__name__)


_OP_FIRE_RE = re.compile(r"^op\.(.+)\.fire$")


def register(bus) -> None:
    """Subscribe metric-recording handlers on the bus.

    The handlers themselves take an event payload only; we listen by name and
    bump labels accordingly.
    """

    async def on_message_captured(p: dict) -> None:
        try:
            messages_ingested.labels(
                provider=str(p.get("provider", "unknown")),
                boss_id=str(p.get("boss_id", "0")),
            ).inc()
        except Exception:
            log.exception("metrics: on_message_captured failed")

    async def on_note_updated(p: dict) -> None:
        try:
            note_updates.labels(
                boss_id=str(p.get("boss_id", "0")),
                status=str(p.get("status", "ok")),
            ).inc()
        except Exception:
            log.exception("metrics: on_note_updated failed")

    async def on_outbound_send(p: dict) -> None:
        try:
            outbound.labels(
                channel=str(p.get("provider", "unknown")),
                status=str(p.get("status", "queued")),
            ).inc()
        except Exception:
            log.exception("metrics: on_outbound_send failed")

    bus.subscribe("message.captured", on_message_captured)
    bus.subscribe("note.updated", on_note_updated)
    bus.subscribe("outbound.send", on_outbound_send)

    # op.<name>.fire is dynamic — wrap publish to count, but the bus has no
    # wildcard subscribe so we attach via a publish hook on the dispatcher
    # registry. Cleanest path: subscribe at registration time per known op.
    from src.agents.registry import OperationRegistry
    for op_cls in OperationRegistry.all():
        ev_name = f"op.{op_cls._op_config.name}.fire"

        async def _on_fire(p: dict, _name: str = op_cls._op_config.name) -> None:
            try:
                op_fires.labels(op_name=_name).inc()
            except Exception:
                log.exception("metrics: on_op_fire failed")

        bus.subscribe(ev_name, _on_fire)

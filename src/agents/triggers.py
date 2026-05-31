import asyncio
from dataclasses import dataclass
from typing import Callable


def parse_window(s: str) -> float:
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) * 60
    if s.endswith("h"):
        return float(s[:-1]) * 3600
    return float(s)


@dataclass
class Debounce:
    key: str  # e.g. "boss_id,chat_id"
    window: str  # e.g. "10m"

    @property
    def window_sec(self):
        return parse_window(self.window)


@dataclass
class Threshold:
    key: str
    count: int


@dataclass
class TriggerSpec:
    op_name: str
    event: str
    debounce: Debounce | None = None
    threshold: Threshold | None = None
    key_fn: Callable[[dict], str] = lambda e: ""


_TRIGGER_REGISTRY: list[TriggerSpec] = []


def trigger(
    *,
    op: str,
    event: str,
    debounce: Debounce | None = None,
    threshold: Threshold | None = None,
    on_demand_tools=(),
):
    def deco(cls_or_fn):
        # Build key_fn from debounce/threshold key spec
        keys = (debounce.key if debounce else threshold.key).split(",")

        def kfn(e: dict) -> str:
            return ":".join(f"{k}={e.get(k.strip(), '')}" for k in keys)

        _TRIGGER_REGISTRY.append(
            TriggerSpec(
                op_name=op,
                event=event,
                debounce=debounce,
                threshold=threshold,
                key_fn=kfn,
            )
        )
        return cls_or_fn

    return deco


class TriggerEngine:
    def __init__(self, bus):
        self.bus = bus
        self._debounce_timers: dict[str, asyncio.TimerHandle] = {}
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def attach_all(self):
        for spec in _TRIGGER_REGISTRY:
            self._attach_one(spec)

    def _attach_one(self, spec: TriggerSpec):
        async def handler(event: dict):
            key = f"{spec.op_name}:{spec.event}:{spec.key_fn(event)}"
            async with self._lock:
                if spec.threshold:
                    self._counters[key] = self._counters.get(key, 0) + 1
                    if self._counters[key] >= spec.threshold.count:
                        await self._fire(spec, event, "threshold")
                        self._counters[key] = 0
                        self._cancel_debounce(key)
                        return
                if spec.debounce:
                    self._cancel_debounce(key)
                    loop = asyncio.get_event_loop()
                    self._debounce_timers[key] = loop.call_later(
                        spec.debounce.window_sec,
                        lambda: asyncio.create_task(
                            self._fire(spec, event, "debounce", key)
                        ),
                    )

        self.bus.subscribe(spec.event, handler)

    def _cancel_debounce(self, key):
        t = self._debounce_timers.pop(key, None)
        if t:
            t.cancel()

    async def _fire(self, spec, event, reason, key=None):
        if key:
            self._debounce_timers.pop(key, None)
        await self.bus.publish(
            f"op.{spec.op_name}.fire",
            {
                "reason": reason,
                "source_event": event,
                "boss_id": event.get("boss_id"),
            },
        )

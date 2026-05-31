import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Protocol

log = logging.getLogger(__name__)

EventName = str
EventPayload = dict
Handler = Callable[[EventPayload], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: EventName, payload: EventPayload) -> None: ...
    def subscribe(self, event: EventName, handler: Handler) -> None: ...


class InMemoryEventBus:
    def __init__(self, handler_timeout_s: float = 10.0):
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._timeout = handler_timeout_s

    def subscribe(self, event: EventName, handler: Handler) -> None:
        self._subs[event].append(handler)

    async def publish(self, event: EventName, payload: EventPayload) -> None:
        handlers = list(self._subs.get(event, []))
        if not handlers:
            return

        async def safe(h: Handler) -> None:
            try:
                await asyncio.wait_for(h(payload), timeout=self._timeout)
            except Exception:
                log.exception(
                    "event handler error",
                    extra={"event": event, "handler": h.__qualname__},
                )

        await asyncio.gather(*(safe(h) for h in handlers), return_exceptions=True)

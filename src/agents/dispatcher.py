import asyncio

from src.agents.context import build_context, trace_op
from src.agents.registry import OperationRegistry


class OperationDispatcher:
    def __init__(self, bus, app_state):
        self.bus = bus
        self.app_state = app_state
        self._sem_by_bot_acc: dict[int, asyncio.Semaphore] = {}

    def attach_all(self):
        for op_cls in OperationRegistry.all():
            cfg = op_cls._op_config
            for evname in cfg.triggered_by:
                self.bus.subscribe(evname, self._make_handler(op_cls))

    def _make_handler(self, op_cls):
        cfg = op_cls._op_config

        async def handler(event):
            if cfg.when and not cfg.when(event):
                return
            ctx = await build_context(cfg.deps_type, event, self.app_state)
            boss_id = event.get("boss_id")
            bot_acc_id = event.get("bot_account_id", 0)
            sem = self._sem_by_bot_acc.setdefault(
                bot_acc_id,
                asyncio.Semaphore(cfg.max_concurrency_per_bot_account),
            )
            with trace_op(cfg.name, boss_id):
                async with sem:
                    await asyncio.wait_for(
                        op_cls().handle(event, ctx), timeout=cfg.timeout_s
                    )

        return handler

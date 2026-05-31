import asyncio
import hashlib
import json
import time

from src.repositories.base import BossContext
from src.repositories.tool_call_log import ToolCallLogRepo
from src.tools import registry
from src.tools.base import ToolContext, ToolDef, ToolResult


class ToolDispatcher:
    def __init__(self, pool):
        self.pool = pool

    async def call_batch(
        self, calls: list, ctx: ToolContext
    ) -> list[tuple[str, ToolResult]]:
        """Calls is list of ToolCall (from LLMResponse). Split into parallel/sequential."""
        results: list[tuple[str, ToolResult]] = []
        parallel: list = []
        sequential: list = []
        for c in calls:
            t = registry.get(c.name)
            (parallel if t.parallel_safe else sequential).append((c, t))
        # Parallel batch
        if parallel:
            par_results = await asyncio.gather(
                *(self._invoke(c, t, ctx) for c, t in parallel)
            )
            results.extend(par_results)
        # Sequential
        for c, t in sequential:
            results.append(await self._invoke(c, t, ctx))
        return results

    async def _invoke(
        self, call, tool_def: ToolDef, ctx: ToolContext
    ) -> tuple[str, ToolResult]:
        t0 = time.time()
        args_hash = hashlib.sha256(
            json.dumps(call.arguments, sort_keys=True).encode()
        ).hexdigest()[:16]
        try:
            result = await asyncio.wait_for(
                tool_def.handler(ctx=ctx, **call.arguments),
                timeout=tool_def.timeout_s,
            )
            status = "ok"
            error = None
        except asyncio.TimeoutError:
            result = ToolResult(content=None, error="timeout")
            status = "timeout"
            error = "timeout"
        except Exception as e:
            result = ToolResult(content=None, error=str(e))
            status = "error"
            error = str(e)
        latency_ms = int((time.time() - t0) * 1000)
        await ToolCallLogRepo(
            self.pool, BossContext(ctx.boss_id, ctx.boss_role)
        ).insert(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            tool_name=tool_def.name,
            args_hash=args_hash,
            status=status,
            latency_ms=latency_ms,
            error=error,
        )
        return call.id, result

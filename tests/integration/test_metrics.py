"""H2: Prometheus /metrics + trace propagation.

Verifies:
  - /metrics endpoint serves Prometheus exposition format
  - All key collectors appear as HELP lines in the output
  - Bus events bump the right counters (message.captured, note.updated,
    outbound.send)
  - LLMGateway records llm_calls + llm_latency on success
  - trace_op propagates trace_id/span_id into structlog contextvars
  - Cache hit ratio job updates the gauge from token_usage rows
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
import structlog
from fastapi.testclient import TestClient

from src.events.bus import InMemoryEventBus
from src.infra.metrics import (
    cache_hit_ratio,
    llm_calls,
    messages_ingested,
    note_updates,
    outbound,
)
from src.infra.metrics_subscriber import register as register_metrics


@pytest.fixture
def app_client(boss_user):
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "")
    from src import main as main_mod
    with TestClient(main_mod.app) as client:
        yield client, boss_user


def test_metrics_endpoint_exposes_collectors(app_client):
    client, _ = app_client
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Every collector we declared should be advertised via a HELP line.
    for name in (
        "messages_ingested_total",
        "note_updates_total",
        "llm_calls_total",
        "llm_call_latency_seconds",
        "outbound_messages_total",
        "retrieval_stage_latency_seconds",
        "tool_call_latency_seconds",
        "llm_cache_hit_ratio",
        "active_sessions",
        "llm_cost_usd_total",
        "op_fires_total",
    ):
        assert f"# HELP {name}" in body, f"missing {name} in /metrics"


@pytest.mark.asyncio
async def test_message_captured_bumps_counter():
    bus = InMemoryEventBus()
    register_metrics(bus)
    before = messages_ingested.labels(provider="zalo", boss_id="42")._value.get()
    await bus.publish(
        "message.captured",
        {"provider": "zalo", "boss_id": 42, "message_id": 1},
    )
    after = messages_ingested.labels(provider="zalo", boss_id="42")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_outbound_send_bumps_counter():
    bus = InMemoryEventBus()
    register_metrics(bus)
    before = outbound.labels(channel="zalo", status="queued")._value.get()
    await bus.publish(
        "outbound.send",
        {"provider": "zalo", "boss_id": 1, "chat_id": "c", "content": "hi",
         "trigger": "test", "status": "queued"},
    )
    after = outbound.labels(channel="zalo", status="queued")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_note_updated_bumps_counter():
    bus = InMemoryEventBus()
    register_metrics(bus)
    before = note_updates.labels(boss_id="1", status="ok")._value.get()
    await bus.publish(
        "note.updated",
        {"group_note_id": 1, "boss_id": 1, "status": "ok"},
    )
    after = note_updates.labels(boss_id="1", status="ok")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_op_fire_bumps_counter():
    """op_fires is incremented for every registered op when op.<name>.fire publishes."""
    from src.agents.registry import OperationRegistry
    from src.infra.metrics import op_fires

    bus = InMemoryEventBus()
    register_metrics(bus)
    ops = list(OperationRegistry.all())
    if not ops:
        pytest.skip("no ops registered")
    op = ops[0]
    name = op._op_config.name
    before = op_fires.labels(op_name=name)._value.get()
    await bus.publish(f"op.{name}.fire", {"boss_id": 1})
    after = op_fires.labels(op_name=name)._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_trace_op_binds_structlog_context():
    from src.agents.context import current, trace_op

    structlog.contextvars.clear_contextvars()
    with trace_op("test_op", boss_id=7) as tc:
        # Native trace ctx
        cur = current()
        assert cur is not None
        assert cur.trace_id == tc.trace_id
        # structlog contextvars must include trace_id, span_id, op, boss_id
        merged = structlog.contextvars.get_contextvars()
        assert merged.get("trace_id") == tc.trace_id
        assert merged.get("span_id") == tc.span_id
        assert merged.get("op") == "test_op"
        assert merged.get("boss_id") == 7
    # After exit, ctx must be cleared
    assert current() is None
    assert "trace_id" not in structlog.contextvars.get_contextvars()


@pytest.mark.asyncio
async def test_cache_hit_ratio_job(db_pool, boss_user):
    from src.scheduler.jobs.cache_hit_ratio import job

    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO token_usage
              (boss_id, feature, operation, provider, model,
               tokens_in, tokens_out, tokens_cached, latency_ms,
               cost_usd, cost_saved_cache_usd, status,
               gen_ai_system, gen_ai_request_model, gen_ai_response_model,
               gen_ai_operation_name)
            VALUES ($1,'dm_general','dm_responder','openai','gpt-4o-mini',
                    1000,200,400,300,$2,$3,'ok',
                    'openai','gpt-4o-mini','gpt-4o-mini','chat')
            """,
            boss_user["id"], Decimal("0.001"), Decimal("0.0004"),
        )

    class _State:
        pass
    state = _State()
    state.db_pool = db_pool

    await job(state)
    # ratio = 400/1000 = 0.4
    ratio = cache_hit_ratio.labels(
        feature="dm_general", model="gpt-4o-mini"
    )._value.get()
    assert ratio == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_llm_gateway_records_metrics(db_pool, boss_user):
    """When complete() succeeds the llm_calls counter must go up."""
    from unittest.mock import AsyncMock, patch

    from src.llm.base import ChatMessage, LLMRequest, LLMResponse, LLMUsage
    from src.llm.native import NativeGateway

    # Build a Model-like stub returned by pick_model
    from src.domain.model import Model
    stub_model = Model(
        id=999, name="stub-model", provider="openai",
        endpoint_kind="openai_compat", base_url=None,
        tier="fast", ctx_max=8000, capabilities=["chat"],
    )

    fake_client = AsyncMock()
    fake_client.chat = AsyncMock(return_value=LLMResponse(
        content="ok", tool_calls=[],
        usage=LLMUsage(
            tokens_in=10, tokens_out=5, tokens_cached=0,
            latency_ms=100, model="stub-model", provider="openai",
        ),
        status="ok",
    ))

    gw = NativeGateway(
        pool=db_pool,
        registry=AsyncMock(),
        llm_routes_repo=AsyncMock(),
        feature_budgets_repo=AsyncMock(),
        api_key_provider=AsyncMock(),
    )

    req = LLMRequest(
        feature="dm_general",
        boss_id=boss_user["id"],
        messages=[ChatMessage(role="user", content="hello")],
    )

    before = llm_calls.labels(
        provider="openai", model="stub-model", status="ok", feature="dm_general"
    )._value.get()

    with patch("src.llm.native.apply_budget", new=AsyncMock()), \
         patch("src.llm.native.mark_cache_breakpoint"), \
         patch("src.llm.native.pick_model",
               new=AsyncMock(return_value=(stub_model, 1))), \
         patch.object(gw, "_client_for", new=AsyncMock(return_value=fake_client)):
        resp = await gw.complete(req)

    assert resp.status == "ok"
    after = llm_calls.labels(
        provider="openai", model="stub-model", status="ok", feature="dm_general"
    )._value.get()
    assert after == before + 1

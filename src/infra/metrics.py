"""Prometheus collectors — single module imported wherever counters/histograms
are bumped. Keep label cardinality bounded (boss_id is fine: O(users); never
add free-form text like prompts).
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# --- Counters ----------------------------------------------------------------

messages_ingested = Counter(
    "messages_ingested_total",
    "Inbound messages persisted by the normalizer.",
    ["provider", "boss_id"],
)

note_updates = Counter(
    "note_updates_total",
    "Group-note rebuilds run by the NoteUpdater op.",
    ["boss_id", "status"],
)

llm_calls = Counter(
    "llm_calls_total",
    "LLM completions issued through the gateway.",
    ["provider", "model", "status", "feature"],
)

llm_cost_usd = Counter(
    "llm_cost_usd_total",
    "Cumulative USD billed by the LLM gateway (computed from token_usage).",
    ["provider", "model", "feature"],
)

outbound = Counter(
    "outbound_messages_total",
    "Outbound messages dispatched through OutboundService → channel.",
    ["channel", "status"],
)

op_fires = Counter(
    "op_fires_total",
    "Operations triggered via op.<name>.fire (post debounce/threshold).",
    ["op_name"],
)

# --- Histograms --------------------------------------------------------------

llm_latency = Histogram(
    "llm_call_latency_seconds",
    "Round-trip latency for an LLM call.",
    ["feature", "tier"],
)

retrieval_latency = Histogram(
    "retrieval_stage_latency_seconds",
    "Per-stage latency inside the retrieval pipeline.",
    ["stage"],
)

tool_latency = Histogram(
    "tool_call_latency_seconds",
    "Tool dispatcher invocation latency.",
    ["tool"],
)

# --- Gauges ------------------------------------------------------------------

cache_hit_ratio = Gauge(
    "llm_cache_hit_ratio",
    "Prompt cache hit ratio (tokens_cached / tokens_in) rolling 1h.",
    ["feature", "model"],
)

active_sessions = Gauge(
    "active_sessions",
    "Live inbound bridges per channel (provider × status).",
    ["channel"],
)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "active_sessions",
    "cache_hit_ratio",
    "generate_latest",
    "llm_calls",
    "llm_cost_usd",
    "llm_latency",
    "messages_ingested",
    "note_updates",
    "op_fires",
    "outbound",
    "retrieval_latency",
    "tool_latency",
]

#!/usr/bin/env python
"""End-to-end behavioral self-test for the SMART bot.

Drives the full agent loop with real LLM + real DB, but stubs outbound
side effects (Lark mutations, Telegram/Zalo outbound) so scenarios are
safe to run repeatedly. Captures tool calls and bot replies, asserts
expected behavior, and prints a pass/fail table.

Usage:
    python scripts/self_test.py                      # all scenarios
    python scripts/self_test.py --only "task,note"   # name substring filter
    python scripts/self_test.py --boss "Dat"         # pick test boss
    python scripts/self_test.py --report-md path.md  # custom report path
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(name)-10s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
# Keep our own logger talkative, silence the rest.
logger = logging.getLogger("self_test")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Recorder — tracks what the bot did during a scenario step
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    name: str
    args: dict | str
    result: str


@dataclass
class Recorder:
    tool_calls: list[ToolCall] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    lark_writes: list[tuple[str, dict]] = field(default_factory=list)
    outbound: list[tuple[str, str]] = field(default_factory=list)  # (chat_id, text)

    def reset(self) -> None:
        self.tool_calls.clear()
        self.replies.clear()
        self.lark_writes.clear()
        self.outbound.clear()


# Module-global recorder (single test run; not concurrent).
_REC = Recorder()


# ---------------------------------------------------------------------------
# Stub: Lark client — no real Lark mutations
# ---------------------------------------------------------------------------


def install_lark_stub() -> None:
    """Monkey-patch lark_client to fake all writes. Reads return empty lists by
    default (we inject per-scenario data via stash_lark_records when needed)."""
    from src.infrastructure import lark_client as lark

    _records_by_table: dict[str, list[dict]] = {}

    async def _fake_search(base_token: str, table_id: str, filter_expr: str = "") -> list[dict]:
        return list(_records_by_table.get(table_id, []))

    async def _fake_create(base_token: str, table_id: str, fields: dict) -> dict:
        rid = f"recFAKE_{uuid.uuid4().hex[:8]}"
        row = {"record_id": rid, **fields}
        _records_by_table.setdefault(table_id, []).append(row)
        _REC.lark_writes.append(("create", {"table": table_id, "fields": fields}))
        return row

    async def _fake_update(base_token: str, table_id: str, record_id: str, fields: dict) -> dict:
        _REC.lark_writes.append(("update", {"table": table_id, "record_id": record_id, "fields": fields}))
        # Mutate in place if found.
        for r in _records_by_table.get(table_id, []):
            if r.get("record_id") == record_id:
                r.update(fields)
                return r
        return {"record_id": record_id, **fields}

    async def _fake_delete(base_token: str, table_id: str, record_id: str):
        _REC.lark_writes.append(("delete", {"table": table_id, "record_id": record_id}))
        _records_by_table[table_id] = [
            r for r in _records_by_table.get(table_id, []) if r.get("record_id") != record_id
        ]

    async def _fake_sync_reminder(*a, **kw):
        _REC.lark_writes.append(("sync_reminder", kw or {"args": a}))

    async def _fake_sync_note(*a, **kw):
        _REC.lark_writes.append(("sync_note", kw or {"args": a}))

    lark.search_records = _fake_search  # type: ignore
    lark.create_record = _fake_create   # type: ignore
    lark.update_record = _fake_update   # type: ignore
    lark.delete_record = _fake_delete   # type: ignore
    lark.sync_reminder_to_lark = _fake_sync_reminder  # type: ignore
    lark.sync_note_to_lark = _fake_sync_note  # type: ignore

    # Expose so scenarios can inject pre-existing records.
    install_lark_stub.records = _records_by_table  # type: ignore[attr-defined]


def stash_lark_records(table_id: str, rows: list[dict]) -> None:
    """Pre-populate fake Lark table for a scenario. Call after install_lark_stub()."""
    records = install_lark_stub.records  # type: ignore[attr-defined]
    records.setdefault(table_id, []).extend(rows)


# ---------------------------------------------------------------------------
# Stub: Qdrant — search returns [], upserts are no-ops
# ---------------------------------------------------------------------------


def install_qdrant_stub() -> None:
    from src.infrastructure import qdrant_client as qdrant

    async def _noop_search(*a, **kw):
        return []

    async def _noop_upsert(*a, **kw):
        return None

    async def _noop_ensure(*a, **kw):
        return None

    async def _noop_provision(*a, **kw):
        return None

    async def _noop_delete(*a, **kw):
        return None

    qdrant.search = _noop_search          # type: ignore
    qdrant.upsert = _noop_upsert          # type: ignore
    qdrant.upsert_task = _noop_upsert     # type: ignore
    qdrant.upsert_note = _noop_upsert     # type: ignore
    qdrant.delete_task = _noop_delete     # type: ignore
    qdrant.ensure_collection = _noop_ensure  # type: ignore
    qdrant.provision_collections = _noop_provision  # type: ignore


# ---------------------------------------------------------------------------
# Stub: outbound channel — CapturingMessenger replaces Telegram + Zalo
# ---------------------------------------------------------------------------


def install_capture_messenger() -> None:
    """Replace telegram_singleton._messenger AND register the same capturing
    messenger for every provider in the channel registry."""
    from src.channels.base import BaseMessenger, MessengerCapabilities, OutgoingMessage
    from src.channels import telegram_singleton
    from src.channels import registry as channel_registry

    class _Capture(BaseMessenger):
        channel = "test"
        capabilities = MessengerCapabilities(
            supports_groups=True, supports_group_admin=True,
            supports_invite_links=True, supports_edit=True, supports_delete=True,
            supports_typing=True, supports_photos=True, supports_files=True,
            supports_voice=True, supports_markdown=True,
        )

        async def send_message(self, chat_id, text, *, format="markdown",
                               save_history=True, reply_to_message_id=None):
            _REC.outbound.append((str(chat_id), text))
            _REC.replies.append(text)
            return OutgoingMessage(message_id=str(uuid.uuid4()), chat_id=str(chat_id))

        async def edit_message(self, chat_id, message_id, text, *, format="markdown"):
            # Treat the FINAL state of the placeholder as the reply.
            # We just record every edit; report uses the last.
            _REC.outbound.append((str(chat_id), text))
            if _REC.replies:
                _REC.replies[-1] = text
            else:
                _REC.replies.append(text)

        async def delete_message(self, chat_id, message_id):
            return None

        async def typing(self, chat_id):
            return None

        async def get_bot_id(self):
            return "test-bot"

        # group admin no-ops (return permissive defaults)
        async def get_chat_administrators(self, chat_id):
            return []

        async def get_chat_member(self, chat_id, user_id):
            return {"status": "member"}

        async def add_chat_member(self, chat_id, user_id):
            return True

        async def set_chat_title(self, chat_id, title):
            return True

        async def set_chat_description(self, chat_id, description):
            return True

        async def pin_chat_message(self, chat_id, message_id):
            return True

        async def unpin_all_chat_messages(self, chat_id):
            return True

        async def ban_chat_member(self, chat_id, user_id):
            return True

        async def unban_chat_member(self, chat_id, user_id):
            return True

        async def create_invite_link(self, chat_id, *, member_limit=1, expire_hours=24):
            return "https://t.me/joinchat/FAKE"

    cap = _Capture()
    telegram_singleton._messenger = cap  # type: ignore
    channel_registry.register("telegram", cap)
    channel_registry.register("zalo", cap)
    channel_registry.register("test", cap)


# ---------------------------------------------------------------------------
# Stub: dispatcher — wrap execute() to record calls
# ---------------------------------------------------------------------------


def install_dispatcher_recorder() -> None:
    from src import agent
    orig = agent._dispatcher.execute  # bound method

    async def wrapped(name: str, arguments, ctx) -> str:
        result = await orig(name, arguments, ctx)
        _REC.tool_calls.append(ToolCall(name=name, args=arguments, result=result))
        return result

    agent._dispatcher.execute = wrapped  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Init — mirror cli_test.py, but with stubs and no scheduler
# ---------------------------------------------------------------------------


async def init_services(settings):
    from src import agent, context, db
    from src.channels import telegram_singleton as telegram
    from src.channels import registry as channel_registry
    from src.infrastructure import (
        cohere_client as cohere,
        lark_client as lark,
        openai_client,
        qdrant_client as qdrant,
    )

    database = await db.get_db(settings.db_path)
    context.init_context(database)
    openai_client.init_openai(
        settings.openai_api_key,
        settings.openai_chat_model,
        settings.openai_embedding_model,
    )
    await qdrant.init_qdrant(settings.qdrant_url)
    await cohere.init_cohere(settings.cohere_api_key)
    # Real lark init so token client builds, then we monkey-patch its calls.
    await lark.init_lark(settings.lark_app_id, settings.lark_app_secret)
    await telegram.init_telegram(settings.telegram_bot_token)
    agent.init_agent(settings)

    from src.agent.llm_for_ctx import init_llm_settings
    init_llm_settings(settings)

    from src.container import build_container
    container = await build_container(settings)

    # Install stubs AFTER the real init, so they replace the real calls.
    install_lark_stub()
    install_qdrant_stub()
    install_capture_messenger()
    install_dispatcher_recorder()

    # CRITICAL: do NOT start scheduler — we'd be racing with deadline pushes,
    # reminder fires, etc.

    from src.controllers.message_router import MessageRouter
    router = MessageRouter(container)
    return router


# ---------------------------------------------------------------------------
# Scenario types
# ---------------------------------------------------------------------------


@dataclass
class UserMessage:
    text: str
    is_group: bool = False
    is_mentioned: bool = False
    new_members: list[dict] = field(default_factory=list)
    attachments: list = field(default_factory=list)
    # Override sender — used for O2 to simulate a stranger DMing the bot.
    # When set, chat_id is resolved to the stranger's DM conversation (created
    # in setup) rather than the boss's DM.
    as_sender_key: str = ""  # "long" | "hung" | "stranger" — keys we'll wire in test_ctx


@dataclass
class FireReminder:
    """Directly invoke reminder_agent.send_reminder() with a synthetic row."""
    reminder: dict


@dataclass
class Expect:
    """Declarative assertion against the recorder state since the last step."""
    any_tool_in: set[str] | None = None              # at least one of these tools called
    no_tool_errors: bool = True                      # tool results free of [TOOL_ERROR
    reply_contains_any: list[str] | None = None      # last reply contains any of these (case-insensitive)
    reply_excludes: list[str] | None = None          # last reply must NOT contain any of these
    outbound_to: str | None = None                   # at least one outbound to this chat_id
    custom: Callable[[Recorder], str | None] | None = None  # return None on pass, else reason


@dataclass
class Scenario:
    name: str
    description: str
    steps: list  # mixed list of UserMessage | FireReminder | Expect
    setup: Callable[[dict], None] | None = None       # called with shared test_ctx
    tags: list[str] = field(default_factory=list)
    # LLM tool-call decisions are non-deterministic. Scenarios that exercise
    # the agent loop end-to-end can spuriously fail one in N runs. Bump this
    # to 1 for those — runner retries once on FAIL before reporting.
    retry_on_fail: int = 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    ok: bool
    reason: str = ""


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    steps: list[StepResult]
    tool_calls: list[ToolCall]
    replies: list[str]
    elapsed_s: float
    error: str = ""


def _check_link_actually_handled(platform: str, url_keyword: str = ""):
    """Build a strict expectation: the bot ACTUALLY processed the link.

    PASS only when:
      - web_search tool was called (genuine attempt to learn about the link), OR
      - reply references the URL content via `url_keyword` (when supplied) AND
        contains no hallucination markers.

    Honest disclaimers ("can't access") count as FAIL — they signal the
    capability is missing, not that the test succeeded. The CSV tags such
    scenarios as FEATURE_GAP separately.
    """
    hallucination_markers = [
        "video này nói", "video nói về", "video kể",
        "nội dung video là", "video chiếu",
        "i watched", "in the video", "the video shows",
    ]

    def _check(rec: Recorder) -> str | None:
        tool_names = {tc.name for tc in rec.tool_calls}
        if "fetch_url" in tool_names or "web_search" in tool_names:
            return None
        if not rec.replies:
            return "no reply at all"
        reply = rec.replies[-1].lower()
        if any(m in reply for m in hallucination_markers):
            return f"reply hallucinates {platform} content"
        if url_keyword and url_keyword.lower() in reply:
            return None
        return (
            f"bot did not actually fetch/process the {platform} link — "
            f"no fetch_url/web_search and no URL-keyword match"
        )

    return _check


def _check_expectations(exp: Expect, rec: Recorder) -> StepResult:
    reasons: list[str] = []

    if exp.any_tool_in is not None:
        names = {tc.name for tc in rec.tool_calls}
        hit = exp.any_tool_in & names
        if not hit:
            reasons.append(
                f"expected one of tools {sorted(exp.any_tool_in)}, got {sorted(names) or '∅'}"
            )

    if exp.no_tool_errors:
        for tc in rec.tool_calls:
            if isinstance(tc.result, str) and tc.result.startswith("[TOOL_ERROR"):
                reasons.append(f"tool {tc.name} returned {tc.result[:80]}")

    if exp.reply_contains_any:
        last = rec.replies[-1].lower() if rec.replies else ""
        if not any(kw.lower() in last for kw in exp.reply_contains_any):
            reasons.append(
                f"reply missing all of {exp.reply_contains_any!r}; got {last[:100]!r}"
            )

    if exp.reply_excludes:
        last = rec.replies[-1].lower() if rec.replies else ""
        hits = [kw for kw in exp.reply_excludes if kw.lower() in last]
        if hits:
            reasons.append(f"reply contained forbidden {hits!r}")

    if exp.outbound_to is not None:
        chat_ids = {c for c, _ in rec.outbound}
        if exp.outbound_to not in chat_ids:
            reasons.append(f"no outbound to {exp.outbound_to}; saw {sorted(chat_ids) or '∅'}")

    if exp.custom is not None:
        msg = exp.custom(rec)
        if msg:
            reasons.append(f"custom: {msg}")

    if reasons:
        return StepResult(ok=False, reason=" | ".join(reasons))
    return StepResult(ok=True)


async def _drive_user_message(
    router, msg: UserMessage, test_ctx: dict
) -> None:
    from src.channels.base import IncomingMessage
    boss_id = test_ctx["boss_id"]
    boss_name = test_ctx["boss_name"]

    if msg.as_sender_key:
        sender_id = test_ctx[f"{msg.as_sender_key}_internal_id"]
        sender_name = test_ctx[f"{msg.as_sender_key}_display_name"]
        chat_id = test_ctx[f"{msg.as_sender_key}_conv_id"]
        chat_type = "dm"
    elif msg.is_group:
        sender_id = boss_id
        sender_name = boss_name
        chat_id = test_ctx["group_conv_id"]
        chat_type = "group"
    else:
        sender_id = boss_id
        sender_name = boss_name
        chat_id = test_ctx["dm_conv_id"]
        chat_type = "dm"

    incoming = IncomingMessage(
        channel="test",
        chat_id=chat_id,
        chat_type=chat_type,
        sender_id=sender_id,
        sender_name=sender_name,
        text=msg.text,
        attachments=msg.attachments,
        is_mentioned=msg.is_mentioned,
        new_members=msg.new_members,
        timestamp=int(time.time()),
        group_name=test_ctx.get("group_name", "Test Group") if msg.is_group else "",
    )
    await router.handle(incoming)


async def _drive_fire_reminder(fr: FireReminder, settings) -> None:
    from src import agent
    await agent.send_reminder(fr.reminder, settings)


async def _run_once(scenario: Scenario, router, settings, test_ctx: dict) -> ScenarioResult:
    _REC.reset()
    if scenario.setup:
        scenario.setup(test_ctx)
    step_results: list[StepResult] = []
    t0 = time.monotonic()
    error = ""
    try:
        for step in scenario.steps:
            if isinstance(step, UserMessage):
                await _drive_user_message(router, step, test_ctx)
            elif isinstance(step, FireReminder):
                await _drive_fire_reminder(step, settings)
            elif isinstance(step, _FireFunc):
                await step.fn(step, settings)
            elif isinstance(step, Expect):
                step_results.append(_check_expectations(step, _REC))
            else:
                step_results.append(StepResult(ok=False, reason=f"unknown step type: {type(step).__name__}"))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("scenario %s crashed", scenario.name)

    elapsed = time.monotonic() - t0
    ok = (not error) and all(s.ok for s in step_results) and bool(step_results)
    return ScenarioResult(
        name=scenario.name,
        ok=ok,
        steps=step_results,
        tool_calls=list(_REC.tool_calls),
        replies=list(_REC.replies),
        elapsed_s=elapsed,
        error=error,
    )


def _auto_retry_budget(scenario: Scenario) -> int:
    """Scenarios that drive the agent loop with a UserMessage depend on the
    LLM choosing a tool — non-deterministic. Default 1 retry for those;
    other scenarios (direct FireFunc / FireReminder) stay strict at 0."""
    if scenario.retry_on_fail:
        return scenario.retry_on_fail
    for s in scenario.steps:
        if isinstance(s, UserMessage):
            return 1
    return 0


async def run_scenario(scenario: Scenario, router, settings, test_ctx: dict) -> ScenarioResult:
    print(f"  → {scenario.name} ...", end="", flush=True)
    result = await _run_once(scenario, router, settings, test_ctx)
    attempts = 1
    budget = _auto_retry_budget(scenario)
    # Retry on FAIL when the scenario opted in — covers LLM tool-call jitter.
    while not result.ok and attempts <= budget:
        retry = await _run_once(scenario, router, settings, test_ctx)
        if retry.ok:
            # Merge: keep the first attempt's elapsed for visibility, but
            # promote the retry's outcome so a stable run shows PASS.
            retry.elapsed_s = result.elapsed_s + retry.elapsed_s
            result = retry
            print(f" RETRY-PASS ({result.elapsed_s:.1f}s)")
            return result
        attempts += 1
    print(f" {'PASS' if result.ok else 'FAIL'} ({result.elapsed_s:.1f}s)")
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_table(results: list[ScenarioResult]) -> str:
    headers = ["#", "Scenario", "Result", "Tools", "Time", "Notes"]
    rows: list[list[str]] = []
    for i, r in enumerate(results, 1):
        tools = ", ".join(sorted({tc.name for tc in r.tool_calls})) or "—"
        if r.error:
            note = f"crash: {r.error[:60]}"
        else:
            fail_reasons = [s.reason for s in r.steps if not s.ok]
            note = "; ".join(fail_reasons)[:120] if fail_reasons else "ok"
        rows.append([
            str(i), r.name[:42],
            "✓" if r.ok else "✗",
            tools[:40], f"{r.elapsed_s:.1f}s", note[:80],
        ])

    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    sep = "+".join("-" * (w + 2) for w in widths)
    sep = f"+{sep}+"

    def fmt(row: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(row)) + " |"

    lines = [sep, fmt(headers), sep] + [fmt(r) for r in rows] + [sep]
    return "\n".join(lines)


def render_markdown(results: list[ScenarioResult]) -> str:
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [
        f"# SMART bot — self-test report",
        f"_Generated: {when}_",
        "",
        f"**Result:** {passed}/{total} passed",
        "",
        "| # | Scenario | Result | Tools called | Time | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        tools = ", ".join(sorted({tc.name for tc in r.tool_calls})) or "—"
        if r.error:
            note = f"crash: `{r.error}`"
        else:
            fail_reasons = [s.reason for s in r.steps if not s.ok]
            note = "; ".join(fail_reasons) if fail_reasons else "ok"
        out.append(
            f"| {i} | {r.name} | {'✓' if r.ok else '✗'} | "
            f"`{tools}` | {r.elapsed_s:.1f}s | {note} |"
        )

    out += ["", "## Failure details", ""]
    for r in results:
        if r.ok:
            continue
        out.append(f"### {r.name}")
        if r.error:
            out.append(f"- **crash:** `{r.error}`")
        for s in r.steps:
            if not s.ok:
                out.append(f"- {s.reason}")
        out.append("")
        out.append("**Tool calls:**")
        for tc in r.tool_calls:
            out.append(f"- `{tc.name}` args=`{str(tc.args)[:120]}` → `{tc.result[:120]}`")
        out.append("")
        out.append("**Replies:**")
        for rp in r.replies:
            out.append(f"> {rp[:200]}")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Test bootstrap — pick boss + ensure DM + group conversations
# ---------------------------------------------------------------------------


async def _bootstrap_test_ctx(boss_hint: str | None) -> dict:
    from src import db
    bosses = await db.get_all_bosses()
    if not bosses:
        print("No boss found. Onboard one first.")
        sys.exit(1)
    if boss_hint:
        q = boss_hint.lower()
        matches = [b for b in bosses if q in (b.get("name") or "").lower()]
        if not matches:
            print(f"No boss matches '{boss_hint}'. Available: {[b['name'] for b in bosses]}")
            sys.exit(1)
        boss = matches[0]
    else:
        boss = bosses[0]

    boss_id = boss["chat_id"]
    boss_name = boss.get("name") or "Boss"

    dm_conv = await db.resolve_or_create_conversation("test", f"selftest_dm_{boss_id}", "dm", "")
    group_conv = await db.resolve_or_create_conversation(
        "test", f"selftest_grp_{boss_id}", "group", "Self-Test Group",
    )
    # Link group to this boss so group routing works.
    grp = await db.get_group(group_conv)
    if not grp:
        await db.add_group(
            group_chat_id=group_conv,
            boss_chat_id=boss_id,
            group_name="Self-Test Group",
            project_id=None,
        )

    # Seed fake people in the boss's Lark people table so resolve_person /
    # get_people return something deterministic. Chat IDs mirror real prod
    # shapes — Telegram is numeric, Zalo is alphanumeric — so the resolver
    # has to handle both. We pre-register them in external_identity so the
    # downstream send() routes them through our CapturingMessenger via the
    # mock conversation row.
    lark_people_tbl = boss.get("lark_table_people") or ""
    long_ext_telegram = "999000001"        # Telegram-shaped
    hung_ext_zalo = "zalo_test_hung_002"   # Zalo-shaped
    stranger_ext = "999000003"             # New unknown contact
    long_internal = await db.resolve_or_create_person(
        "telegram", long_ext_telegram, "Long", "",
    )
    hung_internal = await db.resolve_or_create_person(
        "zalo", hung_ext_zalo, "Hùng", "",
    )
    stranger_internal = await db.resolve_or_create_person(
        "telegram", stranger_ext, "Khách Lạ", "",
    )
    # Conversations so telegram_singleton.send() can route to our capture.
    long_conv = await db.resolve_or_create_conversation("telegram", long_ext_telegram, "dm", "")
    hung_conv = await db.resolve_or_create_conversation("zalo", hung_ext_zalo, "dm", "")
    stranger_conv = await db.resolve_or_create_conversation("telegram", stranger_ext, "dm", "")
    if lark_people_tbl:
        stash_lark_records(lark_people_tbl, [
            {"record_id": "recLONG", "Tên": "Long", "Tên gọi": "Long",
             "Chat ID": long_ext_telegram, "Type": "member"},
            {"record_id": "recHUNG", "Tên": "Hùng", "Tên gọi": "Hùng",
             "Chat ID": hung_ext_zalo, "Type": "member"},
        ])

    return {
        "boss": boss,
        "boss_id": boss_id,
        "boss_name": boss_name,
        "dm_conv_id": dm_conv,
        "group_conv_id": group_conv,
        "group_name": "Self-Test Group",
        # long
        "long_conv_id": long_conv,
        "long_internal_id": long_internal,
        "long_display_name": "Long",
        # hung
        "hung_conv_id": hung_conv,
        "hung_internal_id": hung_internal,
        "hung_display_name": "Hùng",
        # stranger (for O2 join-flow scenarios)
        "stranger_conv_id": stranger_conv,
        "stranger_internal_id": stranger_internal,
        "stranger_display_name": "Khách Lạ",
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


SCENARIOS: list[Scenario] = [
    Scenario(
        name="DM: boss tạo task",
        description="Boss DM lệnh tạo task → expect create_task tool",
        steps=[
            UserMessage("ê tạo task: nộp báo cáo doanh thu trước thứ 6 tuần này"),
            Expect(any_tool_in={"create_task"}),
        ],
        tags=["task", "dm"],
        retry_on_fail=1,
    ),
    Scenario(
        name="DM: list tasks",
        description="Liệt kê task → expect list_tasks hoặc search_tasks",
        steps=[
            UserMessage("cho tôi xem danh sách task hiện tại"),
            Expect(any_tool_in={"list_tasks", "search_tasks"}),
        ],
        tags=["task", "dm"],
    ),
    Scenario(
        name="DM: tạo reminder cho mình",
        description="Self-reminder → expect create_reminder",
        steps=[
            UserMessage("nhắc tôi 6h tối mai gọi điện cho khách hàng"),
            Expect(any_tool_in={"create_reminder"}),
        ],
        tags=["reminder", "dm"],
    ),
    Scenario(
        name="DM: smart note (auto-append)",
        description="Khi boss chia sẻ thông tin cá nhân → expect append_note hoặc update_note",
        steps=[
            UserMessage(
                "À nhớ giúp tôi nhé, từ giờ trở đi gọi tôi là 'anh Đạt' chứ không phải 'sếp', "
                "và tôi thích phong cách trao đổi ngắn gọn, không dài dòng."
            ),
            Expect(any_tool_in={"append_note", "update_note"}),
        ],
        tags=["note", "dm"],
        retry_on_fail=1,
    ),
    Scenario(
        name="Group: @mention tạo reminder cho người khác",
        description="Trong group @bot nhắc 1 người → create_reminder với target + source_chat_id",
        steps=[
            UserMessage(
                "@bot nhắc anh Long 5h chiều mai họp review tuần",
                is_group=True, is_mentioned=True,
            ),
            Expect(any_tool_in={"create_reminder"}),
        ],
        tags=["reminder", "group"],
    ),
    Scenario(
        name="Group: @mention tạo task (Telegram assignee)",
        description="@bot giao Long (Chat ID Telegram numeric) → create_task không crash",
        steps=[
            UserMessage(
                "@bot giao Long task: review báo cáo Q2, deadline thứ 6",
                is_group=True, is_mentioned=True,
            ),
            Expect(any_tool_in={"create_task"}, no_tool_errors=True),
        ],
        tags=["task", "group", "telegram"],
    ),
    Scenario(
        name="Group: @mention tạo task (Zalo assignee)",
        description="@bot giao Hùng (Chat ID Zalo alphanum) → create_task không crash",
        steps=[
            UserMessage(
                "@bot giao Hùng task: tổng hợp số liệu khách hàng, deadline thứ 5",
                is_group=True, is_mentioned=True,
            ),
            Expect(any_tool_in={"create_task"}, no_tool_errors=True),
        ],
        tags=["task", "group", "zalo"],
    ),
    Scenario(
        name="Reminder fire: target DM + cc boss + báo vào source group",
        description="Fire send_reminder() với target + source_chat_id → 3 outbound destinations",
        steps=[],  # built dynamically
        tags=["reminder", "fire", "group"],
    ),
    Scenario(
        name="DM: gửi link YouTube",
        description="Boss paste link YouTube → bot phải hoặc gọi web_search, hoặc thừa nhận không xem được trực tiếp (không hallucinate nội dung video)",
        steps=[
            UserMessage("xem video này nói về gì giúp tôi: https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            Expect(
                custom=_check_link_actually_handled("youtube"),
                no_tool_errors=True,
            ),
        ],
        tags=["link", "dm"],
    ),
    Scenario(
        name="DM: gửi link TikTok",
        description="Boss paste link TikTok → bot không hallucinate nội dung; gọi web_search hoặc disclaim",
        steps=[
            UserMessage("video này nội dung gì: https://www.tiktok.com/@user/video/7000000000000000000"),
            Expect(
                custom=_check_link_actually_handled("tiktok"),
                no_tool_errors=True,
            ),
        ],
        tags=["link", "dm"],
    ),
    Scenario(
        name="DM: gửi link bài báo",
        description="Boss paste link tin tức → bot nên gọi web_search để lấy info; nếu không thì disclaim",
        steps=[
            UserMessage("đọc tin này giúp tôi: https://vnexpress.net/the-thao/bong-da/bong-da-trong-nuoc"),
            Expect(
                custom=_check_link_actually_handled("vnexpress", url_keyword="vnexpress"),
                no_tool_errors=True,
            ),
        ],
        tags=["link", "dm", "news"],
    ),
    Scenario(
        name="DM: gửi file đính kèm",
        description="Boss gửi file text + caption → expect bot phản hồi có nội dung (file đã ingest)",
        steps=[
            # Attachment được build trong setup vì cần Attachment dataclass + temp file
        ],
        tags=["file", "dm"],
    ),
    Scenario(
        name="Escalation: task overdue (DM) → assignee DM + boss report",
        description="Task không có Group ID → reminder fire DM tới assignee + boss report",
        steps=[],  # built dynamically
        tags=["escalate", "fire", "dm"],
    ),
    Scenario(
        name="New-member event trong group → bot phải hỏi boss",
        description=(
            "Khi có người mới vào group đã onboarded, bot chủ động DM boss "
            "(qua channel của boss) hỏi có thêm vào team không."
        ),
        steps=[
            UserMessage(
                "",
                is_group=True,
                is_mentioned=False,
                new_members=[{"id": "newcomer_001", "name": "Người Mới", "username": ""}],
            ),
            Expect(
                custom=lambda rec: (
                    None if any("Người Mới" in body for _, body in rec.outbound)
                    else f"bot didn't DM boss about new member; outbound bodies: {[b[:60] for _, b in rec.outbound] or '∅'}"
                ),
                no_tool_errors=True,
            ),
        ],
        tags=["onboard", "group"],
    ),
    Scenario(
        name="Approve join: boss duyệt + stranger được báo qua channel của họ",
        description="Pre-insert pending membership → boss duyệt → approve_join + membership active + stranger nhận outbound",
        steps=[],  # built dynamically
        tags=["onboard", "approve"],
    ),
    Scenario(
        name="Onboard listing isolation: Zalo stranger không thấy boss Telegram",
        description="handle_join_inquiry từ Zalo conv không list được boss có primary_channel='telegram'",
        steps=[],  # built dynamically
        tags=["onboard", "channel", "isolation"],
    ),
    Scenario(
        name="Image attachment: bot nhận diện ảnh",
        description="Boss gửi ảnh nhỏ → bot ingest, reply không crash, có nhắc tới ảnh hoặc nội dung",
        steps=[],  # built dynamically
        tags=["file", "image", "dm"],
    ),
    Scenario(
        name="Reminder fire: source-only (không target) → vào source group",
        description="Reminder có source_chat_id (group), KHÔNG target → expect outbound vào source group",
        steps=[],  # built dynamically
        tags=["reminder", "fire", "source"],
    ),
    Scenario(
        name="Escalation: task từ group, assignee chưa join → reminder vào group",
        description="Task có Group ID + assignee không có Chat ID → reminder fallback vào group thay vì silent",
        steps=[],  # built dynamically
        tags=["escalate", "fire", "group", "fallback"],
    ),
    Scenario(
        name="Request join: stranger gọi request_join → pending row + boss DM",
        description=(
            "Stranger ngữ cảnh DM bot gọi tool request_join trực tiếp → kiểm tra "
            "membership pending được tạo + boss nhận outbound notification."
        ),
        steps=[],  # built dynamically
        tags=["onboard", "request"],
    ),
    Scenario(
        name="C1: Zalo boss + Telegram-only assignee → reminder vào group, KHÔNG DM",
        description=(
            "Boss có primary_channel='zalo'; assignee Long chỉ có identity Telegram. "
            "Task từ group → reminder PHẢI vào group, KHÔNG được DM Long."
        ),
        steps=[],  # built dynamically
        tags=["channel", "isolation"],
    ),
    Scenario(
        name="E2: no-reply timer → bot báo sếp",
        description=(
            "Reminder đã fire tới target > N giờ trước; target không phản hồi → "
            "bot tự DM boss."
        ),
        steps=[],  # built dynamically
        tags=["escalate", "no-reply"],
    ),
    Scenario(
        name="Reminder fire DM-only (self): chỉ boss, KHÔNG group",
        description="Boss tạo reminder cho chính mình trong DM (no target, no source) → fire chỉ DM boss",
        steps=[],  # built dynamically
        tags=["reminder", "fire", "solo"],
    ),
    Scenario(
        name="Reminder fire DM-only (boss → member): target DM + cc boss, KHÔNG group",
        description="Boss DM tạo reminder cho Long (target, no source) → fire DM Long + cc boss, KHÔNG có group post",
        steps=[],  # built dynamically
        tags=["reminder", "fire", "solo"],
    ),
]


def _build_file_scenario(test_ctx: dict) -> Scenario:
    """Send a small text file as attachment. Bot should ingest and surface
    a recognizable keyword from the file in its reply."""
    from src.channels.base import Attachment
    tmp = Path("/tmp/selftest_doc.txt")
    # Distinctive marker so the assertion can verify the bot actually read
    # the file (not just stitching a generic reply).
    tmp.write_text(
        "Báo cáo tuần 21: doanh thu tăng 12%, đơn hàng mới 47 cái. "
        "Khách hàng quan trọng: ZULIPIX và QORANTEK. "
        "Cần follow-up trong tuần tới về hợp đồng năm 2026.",
        encoding="utf-8",
    )
    att = Attachment(
        kind="file", url=str(tmp), mime_type="text/plain",
        filename="bao_cao_tuan.txt", size_bytes=tmp.stat().st_size,
    )

    def _file_check(rec: Recorder) -> str | None:
        if not rec.replies:
            return "no reply"
        last = rec.replies[-1].lower()
        # Strict: bot ACTUALLY read the file → unique keyword shows up. Honest
        # disclaimer is FAIL (file_ingestion gap = missing feature, not pass).
        if "zulipix" in last or "qorantek" in last:
            return None
        return (
            "bot did not read the file content (no unique keyword in reply) — "
            "feature gap, file_ingestion doesn't handle text/plain"
        )

    return Scenario(
        name="DM: gửi file đính kèm",
        description="Boss gửi file text + caption; reply phải reference keyword đặc trưng từ file",
        steps=[
            UserMessage("tóm tắt giúp tôi file này", attachments=[att]),
            Expect(custom=_file_check, no_tool_errors=True),
        ],
        tags=["file", "dm"],
    )


def _build_image_scenario(test_ctx: dict) -> Scenario:
    from src.channels.base import Attachment
    from PIL import Image
    tmp = Path("/tmp/selftest_image.png")
    # Generate a small red square so the LLM has visible content to describe.
    img = Image.new("RGB", (32, 32), color=(220, 30, 30))
    img.save(tmp, format="PNG")
    att = Attachment(
        kind="photo", url=str(tmp), mime_type="image/png",
        filename="selftest_image.png", size_bytes=tmp.stat().st_size,
    )

    def _img_check(rec: Recorder) -> str | None:
        if not rec.replies:
            return "no reply"
        last = rec.replies[-1].lower()
        # Bot's reply should mention image-related concept; for a tiny test PNG
        # the LLM may say "không nhận diện rõ" / "ảnh nhỏ" / mention color etc.
        markers = ["ảnh", "image", "hình", "photo", "bức", "nhỏ", "đỏ", "red"]
        if not any(m in last for m in markers):
            return f"reply doesn't reference the image at all: {last[:120]!r}"
        return None

    return Scenario(
        name="Image attachment: bot nhận diện ảnh",
        description="Boss gửi ảnh PNG nhỏ + caption",
        steps=[
            UserMessage("trong ảnh này có gì?", attachments=[att]),
            Expect(custom=_img_check, no_tool_errors=True),
        ],
        tags=["file", "image", "dm"],
    )


def _build_approve_join_scenario(test_ctx: dict) -> Scenario:
    """Pre-insert a pending membership row, drive boss DM to approve, then
    verify: (1) tool fired, (2) membership active, (3) stranger received an
    outbound notification on their channel."""
    stranger_id = test_ctx["stranger_internal_id"]
    stranger_conv = test_ctx["stranger_conv_id"]
    boss_id = test_ctx["boss_id"]

    async def _seed(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        await db.upsert_membership(
            _db,
            chat_id=stranger_id,
            boss_chat_id=str(boss_id),
            person_type="member",
            name="Khách Lạ",
            status="pending",
            request_info="Xin vào workspace để hỗ trợ dự án 2026",
        )

    async def _verify(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        row = await db.get_membership(_db, stranger_id, str(boss_id))
        if not row:
            raise AssertionError("membership row missing after approve")
        if row.get("status") != "active":
            raise AssertionError(f"membership status still {row.get('status')!r}, expected active")

    def _stranger_got_notice(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if stranger_conv not in chat_ids:
            return (
                f"stranger DM ({stranger_conv}) didn't receive an approval "
                f"notification; outbounds went to {sorted(chat_ids) or '∅'}"
            )
        return None

    return Scenario(
        name="Approve join: boss duyệt + stranger được báo qua channel của họ",
        description="Pre-insert pending membership → boss duyệt → approve_join + membership active + stranger nhận outbound",
        steps=[
            _FireFunc(_seed),
            UserMessage(
                f"Có yêu cầu join từ Khách Lạ (chat_id={stranger_id}). Duyệt nó vào workspace của tôi với role member."
            ),
            Expect(any_tool_in={"approve_join"}, no_tool_errors=True),
            _FireFunc(_verify),
            Expect(custom=_stranger_got_notice),
        ],
        tags=["onboard", "approve"],
    )


def _build_listing_isolation_scenario(test_ctx: dict) -> Scenario:
    """Verify the LIST FILTER is the primary isolation mechanism.

    Test boss "Linh" has primary_channel='telegram'. Calling
    handle_join_inquiry from a Zalo conversation must produce a listing
    that does NOT include Linh — i.e. a Zalo stranger never even sees the
    Telegram boss as a target, so cross-channel mis-pick is impossible
    upstream of `_complete_member`.

    Also verifies the reverse path: a Telegram conv DOES see Linh.
    """
    boss_name = test_ctx["boss_name"]
    hung_conv = test_ctx["hung_conv_id"]    # provider='zalo'
    dm_conv = test_ctx["dm_conv_id"]        # provider='test' — legacy/back-compat path
    long_conv = test_ctx["long_conv_id"]    # provider='telegram' (Long's DM)

    async def _check_zalo_listing(_step, _settings) -> None:
        from src import onboarding
        reply = await onboarding.handle_join_inquiry(hung_conv)
        if boss_name in reply:
            raise AssertionError(
                f"Zalo stranger saw the Telegram boss {boss_name!r} in the listing — "
                f"isolation broken. Reply: {reply[:200]!r}"
            )

    async def _check_telegram_listing(_step, _settings) -> None:
        from src import onboarding
        reply = await onboarding.handle_join_inquiry(long_conv)
        if boss_name not in reply:
            raise AssertionError(
                f"Telegram stranger did NOT see the matching Telegram boss "
                f"{boss_name!r} in the listing — over-aggressive filtering. "
                f"Reply: {reply[:200]!r}"
            )

    return Scenario(
        name="Onboard listing isolation: Zalo stranger không thấy boss Telegram",
        description="handle_join_inquiry filter theo channel — Zalo conv không thấy Telegram boss, Telegram conv vẫn thấy",
        steps=[
            _FireFunc(_check_zalo_listing),
            _FireFunc(_check_telegram_listing),
            # No-op Expect so the scenario has at least one outcome row.
            Expect(custom=lambda rec: None),
        ],
        tags=["onboard", "channel", "isolation"],
    )


def _build_source_only_reminder_scenario(test_ctx: dict) -> Scenario:
    """Fire a reminder with NO target but WITH source_chat_id → outbound goes
    to source group (not boss DM)."""
    boss_id = test_ctx["boss_id"]
    source_group = test_ctx["group_conv_id"]
    fake_reminder = {
        "id": 999_999_998,
        "boss_chat_id": boss_id,
        "target_chat_id": None,
        "target_name": "",
        "source_chat_id": source_group,
        "content": "Source-only reminder fire test",
        "remind_at": int(time.time()),
    }
    return Scenario(
        name="Reminder fire: source-only (không target) → vào source group",
        description="Reminder không có target_chat_id, có source_chat_id → outbound vào source group",
        steps=[
            FireReminder(reminder=fake_reminder),
            Expect(outbound_to=source_group),
        ],
        tags=["reminder", "fire", "source"],
    )


def _build_escalate_scenario(test_ctx: dict) -> Scenario:
    """Inject an overdue task (DM context, known assignee) into Lark stub,
    fire after_deadline_check. Strict: outbound must reach the assignee's
    DM conversation, and the boss must receive a report."""
    boss = test_ctx["boss"]
    tasks_tbl = boss.get("lark_table_tasks") or ""
    long_conv = test_ctx["long_conv_id"]
    long_internal = test_ctx["long_internal_id"]
    boss_id = test_ctx["boss_id"]

    overdue_ms = int(time.time() * 1000) - 2 * 3600 * 1000
    # Unique record id per run so the persistent task_notifications table
    # doesn't suppress the fire (records survive across test runs).
    record_id = f"recOVERDUE_DM_{uuid.uuid4().hex[:8]}"

    def setup(_ctx: dict) -> None:
        if tasks_tbl:
            stash_lark_records(tasks_tbl, [{
                "record_id": record_id,
                "Tên task": "Self-test overdue task DM",
                "Assignee": "Long",
                "Status": "Đang làm",
                "Deadline": overdue_ms,
                # No "Group ID" → DM routing path
            }])

    async def _seed_notif(_step, _settings) -> None:
        # _after_deadline_check only considers tasks that already have a row
        # in `task_notifications` — that row is created when the task is
        # produced via create_task. Mirror that here.
        from src import db
        _db = await db.get_db()
        await db.upsert_task_notification(_db, record_id, str(boss_id), long_internal)

    async def _fire(_step, _settings) -> None:
        from src.scheduler import _after_deadline_check
        await _after_deadline_check()

    def _strict_check(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        # Scheduler dispatches via telegram.send(boss["chat_id"], ...) which
        # resolves boss external id → internal DM conv. The test sees that
        # internal id, not the raw boss_id string. Require: at least 2 distinct
        # outbound destinations AND assignee DM is one of them.
        if long_conv not in chat_ids:
            return f"assignee DM ({long_conv}) didn't get the overdue notice; saw {sorted(chat_ids)}"
        if len(chat_ids) < 2:
            return f"boss didn't get a separate report; outbound only hit {sorted(chat_ids)}"
        return None

    return Scenario(
        name="Escalation: task overdue (DM) → assignee DM + boss report",
        description="Task không có Group ID → reminder route tới assignee DM + boss",
        setup=setup,
        steps=[
            _FireFunc(_seed_notif),
            _FireFunc(_fire),
            Expect(custom=_strict_check, no_tool_errors=True),
        ],
        tags=["escalate", "fire", "dm"],
    )


def _build_solo_self_reminder_scenario(test_ctx: dict) -> Scenario:
    """Self-reminder created in DM: target=None, source=None. Fire must reach
    boss only — never a group, never an unintended DM."""
    boss_id = test_ctx["boss_id"]
    group_conv = test_ctx["group_conv_id"]
    long_conv = test_ctx["long_conv_id"]
    reminder = {
        "id": 999_999_001,
        "boss_chat_id": boss_id,
        "target_chat_id": None,
        "target_name": "",
        "source_chat_id": None,
        "content": "Solo self-reminder test",
        "remind_at": int(time.time()),
    }

    def _strict(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if group_conv in chat_ids:
            return f"leak: group ({group_conv}) got a solo reminder"
        if long_conv in chat_ids:
            return f"leak: third party Long DM ({long_conv}) got a solo reminder"
        if not rec.outbound:
            return "no outbound at all"
        return None

    return Scenario(
        name="Reminder fire DM-only (self): chỉ boss, KHÔNG group",
        description="Self-reminder không có target / source → chỉ boss DM",
        steps=[FireReminder(reminder=reminder), Expect(custom=_strict)],
        tags=["reminder", "fire", "solo"],
    )


def _build_solo_target_reminder_scenario(test_ctx: dict) -> Scenario:
    """DM boss → "nhắc Long ...": target=Long, source=None. Fire must reach
    Long DM + boss cc — never the group (boss didn't ask via group)."""
    boss_id = test_ctx["boss_id"]
    group_conv = test_ctx["group_conv_id"]
    long_conv = test_ctx["long_conv_id"]
    reminder = {
        "id": 999_999_002,
        "boss_chat_id": boss_id,
        "target_chat_id": long_conv,
        "target_name": "Long",
        "source_chat_id": None,
        "content": "DM-target solo reminder test",
        "remind_at": int(time.time()),
    }

    def _strict(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if long_conv not in chat_ids:
            return f"target Long DM didn't get the reminder; saw {sorted(chat_ids)}"
        if group_conv in chat_ids:
            return f"leak: group ({group_conv}) got a DM-created reminder it shouldn't see"
        return None

    return Scenario(
        name="Reminder fire DM-only (boss → member): target DM + cc boss, KHÔNG group",
        description="Reminder có target, không có source → DM target + cc boss, không touch group",
        steps=[FireReminder(reminder=reminder), Expect(custom=_strict)],
        tags=["reminder", "fire", "solo"],
    )


def _build_no_reply_escalation_scenario(test_ctx: dict) -> Scenario:
    """E2: pre-insert a fake outbound_messages row dated 4h ago with no
    matching inbound, run _check_no_reply_reminders, expect boss to receive
    an escalation DM and the row's `escalated` flag to flip to 1."""
    boss_id = test_ctx["boss_id"]
    long_conv = test_ctx["long_conv_id"]
    outbound_id_holder: dict[str, int | None] = {"id": None}

    async def _seed(_step, _settings) -> None:
        from src import db
        conn = await db.get_db()
        cur = await conn.execute(
            """
            INSERT INTO outbound_messages
                (boss_chat_id, to_chat_id, to_name, content, trigger_type, created_at)
            VALUES (?, ?, ?, ?, 'reminder', datetime('now', '-4 hours'))
            """,
            (str(boss_id), long_conv, "Long", "Nhắc Long nộp báo cáo Q2"),
        )
        await conn.commit()
        outbound_id_holder["id"] = cur.lastrowid

    async def _fire(_step, _settings) -> None:
        from src.scheduler import _check_no_reply_reminders
        await _check_no_reply_reminders()

    async def _verify(_step, _settings) -> None:
        from src import db
        conn = await db.get_db()
        oid = outbound_id_holder["id"]
        async with conn.execute(
            "SELECT escalated FROM outbound_messages WHERE id = ?", (oid,),
        ) as cur:
            row = await cur.fetchone()
        if not row or row["escalated"] != 1:
            raise AssertionError(
                f"outbound row id={oid} not marked escalated; row={dict(row) if row else None}"
            )

    def _check_outbound(rec: Recorder) -> str | None:
        # Boss must receive at least one outbound about Long.
        for _, body in rec.outbound:
            if "long" in body.lower() and "phản hồi" in body.lower():
                return None
        return f"boss didn't get a no-reply escalation about Long; bodies: {[b[:80] for _, b in rec.outbound] or '∅'}"

    return Scenario(
        name="E2: no-reply timer → bot báo sếp",
        description="Reminder gửi 4h trước, target im lặng → _check_no_reply_reminders escalate",
        steps=[
            _FireFunc(_seed),
            _FireFunc(_fire),
            Expect(custom=_check_outbound, no_tool_errors=True),
            _FireFunc(_verify),
        ],
        tags=["escalate", "no-reply"],
    )


def _build_channel_isolation_scenario(test_ctx: dict) -> Scenario:
    """C1: temporarily flip the test boss's primary_channel to 'zalo' so the
    existing Telegram-shaped assignee Long looks cross-channel. Expect the
    deadline reminder to land in the group only, not in Long's DM.

    The test reverts primary_channel after the scenario to keep other tests
    deterministic.
    """
    boss = test_ctx["boss"]
    tasks_tbl = boss.get("lark_table_tasks") or ""
    boss_id = test_ctx["boss_id"]
    group_conv = test_ctx["group_conv_id"]
    long_conv = test_ctx["long_conv_id"]

    overdue_ms = int(time.time() * 1000) - 2 * 3600 * 1000
    record_id = f"recC1_{uuid.uuid4().hex[:8]}"
    prev_channel: dict[str, str | None] = {"value": None}

    def setup(_ctx: dict) -> None:
        if tasks_tbl:
            stash_lark_records(tasks_tbl, [{
                "record_id": record_id,
                "Tên task": "C1 cross-channel task",
                "Assignee": "Long",
                "Status": "Đang làm",
                "Deadline": overdue_ms,
                "Group ID": group_conv,
            }])

    async def _flip_to_zalo(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        async with _db.execute(
            "SELECT primary_channel FROM bosses WHERE chat_id = ?", (str(boss_id),)
        ) as cur:
            row = await cur.fetchone()
        prev_channel["value"] = row["primary_channel"] if row else None
        await _db.execute(
            "UPDATE bosses SET primary_channel = 'zalo' WHERE chat_id = ?",
            (str(boss_id),),
        )
        await _db.commit()
        # Seed notification row so _after_deadline_check picks the task up.
        await db.upsert_task_notification(_db, record_id, str(boss_id), None)

    async def _fire(_step, _settings) -> None:
        from src.scheduler import _after_deadline_check
        await _after_deadline_check()

    async def _restore(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        await _db.execute(
            "UPDATE bosses SET primary_channel = ? WHERE chat_id = ?",
            (prev_channel["value"], str(boss_id)),
        )
        await _db.commit()

    def _strict(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if group_conv not in chat_ids:
            return f"group ({group_conv}) didn't get the reminder; saw {sorted(chat_ids) or '∅'}"
        if long_conv in chat_ids:
            return (
                f"channel leak: Long's Telegram DM ({long_conv}) received the "
                f"reminder despite boss being on Zalo"
            )
        return None

    return Scenario(
        name="C1: Zalo boss + Telegram-only assignee → reminder vào group, KHÔNG DM",
        description="Verify channel isolation drops cross-channel assignee DM, group still gets it",
        setup=setup,
        steps=[
            _FireFunc(_flip_to_zalo),
            _FireFunc(_fire),
            Expect(custom=_strict, no_tool_errors=True),
            _FireFunc(_restore),
        ],
        tags=["channel", "isolation"],
    )


def _build_request_join_scenario(test_ctx: dict) -> Scenario:
    """Call request_join service directly with a stranger ChatContext. Verify
    that the pending membership lands in DB and the boss receives an outbound
    notification on whatever channel they registered with."""
    from src.context import ChatContext
    boss = test_ctx["boss"]
    boss_id = test_ctx["boss_id"]
    stranger_id = test_ctx["stranger_internal_id"]
    stranger_conv = test_ctx["stranger_conv_id"]

    # Build a minimal ChatContext shaped like what onboarding would produce for
    # a stranger (no membership yet, chat_id == stranger DM conv).
    stranger_ctx = ChatContext(
        sender_chat_id=stranger_id,
        sender_name="Khách Lạ",
        sender_type="unknown",
        boss_chat_id="",        # stranger has no boss yet
        boss_name="",
        lark_base_token="",
        lark_table_people="",
        lark_table_tasks="",
        lark_table_projects="",
        lark_table_ideas="",
        lark_table_reminders="",
        lark_table_notes="",
        chat_id=stranger_conv,
        is_group=False,
        group_name="",
        messages_collection="",
        tasks_collection="",
    )

    async def _seed_clear(_step, _settings) -> None:
        # Self-test re-runs share DB; clean any prior pending row for this
        # stranger so the assertion is meaningful.
        from src import db
        _db = await db.get_db()
        await _db.execute(
            "DELETE FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
            (stranger_id, str(boss_id)),
        )
        await _db.commit()

    async def _call_request_join(_step, _settings) -> None:
        from src.services import join_service
        await join_service.request_join(
            stranger_ctx,
            target_boss_id=str(boss_id),
            role="member",
            intro="Em muốn vào workspace để hỗ trợ dự án 2026.",
        )

    async def _verify(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        row = await db.get_membership(_db, stranger_id, str(boss_id))
        if not row:
            raise AssertionError("no pending membership row after request_join")
        if row.get("status") != "pending":
            raise AssertionError(f"status={row.get('status')!r}, expected 'pending'")

    def _check(rec: Recorder) -> str | None:
        # request_join sends one DM to the boss's chat. Self-test capture
        # records every outbound — at least one is required.
        if not rec.outbound:
            return "boss didn't receive any outbound notification of the join request"
        return None

    return Scenario(
        name="Request join: stranger gọi request_join → pending row + boss DM",
        description="Verify request_join service tạo pending membership + thông báo boss qua channel của boss",
        steps=[
            _FireFunc(_seed_clear),
            _FireFunc(_call_request_join),
            Expect(custom=_check),
            _FireFunc(_verify),
        ],
        tags=["onboard", "request"],
    )


def _build_escalate_group_unknown_assignee_scenario(test_ctx: dict) -> Scenario:
    """Task from a group context with an assignee who has NO Chat ID in Lark.
    The deadline reminder must fall back to the source group, NOT just go silent."""
    boss = test_ctx["boss"]
    tasks_tbl = boss.get("lark_table_tasks") or ""
    people_tbl = boss.get("lark_table_people") or ""
    group_conv = test_ctx["group_conv_id"]
    boss_id = test_ctx["boss_id"]

    overdue_ms = int(time.time() * 1000) - 2 * 3600 * 1000
    record_id = f"recOVERDUE_GRP_{uuid.uuid4().hex[:8]}"

    def setup(_ctx: dict) -> None:
        # Inject overdue task with Group ID set, assignee "Nam" who exists in
        # Lark People row but has NO Chat ID (the "chưa join workspace" case).
        if tasks_tbl:
            stash_lark_records(tasks_tbl, [{
                "record_id": record_id,
                "Tên task": "Self-test overdue task GROUP",
                "Assignee": "Nam",
                "Status": "Đang làm",
                "Deadline": overdue_ms,
                "Group ID": group_conv,
            }])
        if people_tbl:
            stash_lark_records(people_tbl, [{
                "record_id": "recNAM",
                "Tên": "Nam",
                "Tên gọi": "Nam",
                # No "Chat ID" — assignee chưa join workspace
                "Type": "member",
            }])

    async def _seed_notif(_step, _settings) -> None:
        from src import db
        _db = await db.get_db()
        # No assignee_chat_id because assignee chưa join
        await db.upsert_task_notification(_db, record_id, str(boss_id), None)

    async def _fire(_step, _settings) -> None:
        from src.scheduler import _after_deadline_check
        await _after_deadline_check()

    def _strict_check(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if group_conv not in chat_ids:
            return (
                f"task has Group ID but reminder didn't fall back to the group "
                f"({group_conv}); saw outbounds to {sorted(chat_ids) or '∅'}"
            )
        return None

    return Scenario(
        name="Escalation: task từ group, assignee chưa join → reminder vào group",
        description="Task có Group ID + assignee không có Chat ID → fallback vào group",
        setup=setup,
        steps=[
            _FireFunc(_seed_notif),
            _FireFunc(_fire),
            Expect(custom=_strict_check, no_tool_errors=True),
        ],
        tags=["escalate", "fire", "group", "fallback"],
    )


@dataclass
class _FireFunc:
    """Step that invokes an async callable(step, settings) — for custom direct-call flows."""
    fn: Callable


def _build_fire_reminder_scenario(test_ctx: dict) -> Scenario:
    """Reminder fire with BOTH target_chat_id AND source_chat_id (group).
    Strict assertion: target gets DM, boss gets cc, AND source group also
    receives a public 'vừa nhắc' notice (the auto-detect-and-report-back-
    to-group behaviour)."""
    boss_id = test_ctx["boss_id"]
    target = test_ctx["dm_conv_id"]
    source_group = test_ctx["group_conv_id"]
    fake_reminder = {
        "id": 999_999_999,
        "boss_chat_id": boss_id,
        "target_chat_id": target,
        "target_name": "Self-Test Target",
        "source_chat_id": source_group,
        "content": "Test fire — nộp báo cáo",
        "remind_at": int(time.time()),
    }

    def _strict(rec: Recorder) -> str | None:
        chat_ids = {c for c, _ in rec.outbound}
        if target not in chat_ids:
            return f"target DM ({target}) didn't get the reminder; saw {sorted(chat_ids)}"
        if source_group not in chat_ids:
            return (
                f"source group ({source_group}) didn't get the public notice; "
                f"saw {sorted(chat_ids)}"
            )
        return None

    return Scenario(
        name="Reminder fire: target DM + cc boss + báo vào source group",
        description="Fire send_reminder() với target + source_chat_id → 3 outbound",
        steps=[
            FireReminder(reminder=fake_reminder),
            Expect(custom=_strict),
        ],
        tags=["reminder", "fire", "group"],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async(args) -> int:
    from src.config import Settings
    settings = Settings()

    print("Bootstrapping services (real DB + LLM, stubbed Lark/outbound)…")
    router = await init_services(settings)

    test_ctx = await _bootstrap_test_ctx(args.boss)
    print(f"Test boss: {test_ctx['boss_name']} ({test_ctx['boss_id']})")
    print(f"DM conv:    {test_ctx['dm_conv_id']}")
    print(f"Group conv: {test_ctx['group_conv_id']}")
    print()

    # Replace placeholders with runtime-built versions that need test_ctx.
    dynamic_builders = {
        "Reminder fire: target DM + cc boss + báo vào source group": _build_fire_reminder_scenario,
        "DM: gửi file đính kèm": _build_file_scenario,
        "Escalation: task overdue (DM) → assignee DM + boss report": _build_escalate_scenario,
        "Approve join: boss duyệt + stranger được báo qua channel của họ": _build_approve_join_scenario,
        "Onboard listing isolation: Zalo stranger không thấy boss Telegram": _build_listing_isolation_scenario,
        "Image attachment: bot nhận diện ảnh": _build_image_scenario,
        "Reminder fire: source-only (không target) → vào source group": _build_source_only_reminder_scenario,
        "Escalation: task từ group, assignee chưa join → reminder vào group": _build_escalate_group_unknown_assignee_scenario,
        "Request join: stranger gọi request_join → pending row + boss DM": _build_request_join_scenario,
        "C1: Zalo boss + Telegram-only assignee → reminder vào group, KHÔNG DM": _build_channel_isolation_scenario,
        "E2: no-reply timer → bot báo sếp": _build_no_reply_escalation_scenario,
        "Reminder fire DM-only (self): chỉ boss, KHÔNG group": _build_solo_self_reminder_scenario,
        "Reminder fire DM-only (boss → member): target DM + cc boss, KHÔNG group": _build_solo_target_reminder_scenario,
    }
    scenarios = []
    for s in SCENARIOS:
        builder = dynamic_builders.get(s.name)
        scenarios.append(builder(test_ctx) if builder else s)

    # Filter
    if args.only:
        needles = [n.strip().lower() for n in args.only.split(",") if n.strip()]
        scenarios = [
            s for s in scenarios
            if any(n in s.name.lower() or n in " ".join(s.tags) for n in needles)
        ]
    if not scenarios:
        print("(no scenarios matched filter)")
        return 1

    print(f"Running {len(scenarios)} scenario(s):")
    t0 = time.monotonic()
    results: list[ScenarioResult] = []
    for sc in scenarios:
        res = await run_scenario(sc, router, settings, test_ctx)
        results.append(res)
    elapsed = time.monotonic() - t0

    print()
    print(render_table(results))
    print(f"\nTotal: {sum(r.ok for r in results)}/{len(results)} passed in {elapsed:.1f}s")

    report_path = Path(args.report_md)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(results), encoding="utf-8")
    print(f"Markdown report: {report_path}")

    # Cleanup — close httpx clients / qdrant client so asyncio.run can exit.
    try:
        from src import db
        from src.channels import telegram_singleton as telegram
        from src.infrastructure import (
            cohere_client as cohere,
            lark_client as lark,
            qdrant_client as qdrant,
        )
        await telegram.close_telegram()
        await lark.close_lark()
        await cohere.close_cohere()
        await qdrant.close_qdrant()
        await db.close_db()
    except Exception:
        pass

    return 0 if all(r.ok for r in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="SMART bot self-test harness")
    parser.add_argument("--boss", default=None, help="Boss name substring (default: first boss)")
    parser.add_argument("--only", default=None, help="Filter by name/tag substring (comma-sep)")
    parser.add_argument(
        "--report-md", default="data/self_test_report.md",
        help="Where to write the markdown report",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

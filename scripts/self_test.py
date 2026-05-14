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


def _check_link_handling(platform: str, url_keyword: str = ""):
    """Build a custom expectation for link scenarios.

    PASS conditions:
      - bot called web_search (genuine attempt to learn about the link), OR
      - reply contains an honest disclaimer (can't access / can't watch / ...)
        AND does NOT contain hallucination markers ("video này nói về", ...)
    FAIL when reply describes specific video content without having fetched it.
    """
    hallucination_markers = [
        "video này nói", "video nói về", "video kể",
        "nội dung video là", "video chiếu",
        "i watched", "in the video", "the video shows",
    ]
    disclaimers = [
        # "không X"
        "không thể", "không xem", "không truy cập", "không đọc",
        "không phân tích trực tiếp", "không xem trực tiếp",
        "không mở", "không mở được", "không trực tiếp",
        "không có khả năng",
        # "chưa X" (bot's common phrasing — modest disclaim)
        "chưa xem", "chưa đọc", "chưa truy cập", "chưa thể",
        "chưa mở", "chưa fetch",
        # English
        "cannot access", "can't watch", "can't access",
        "cannot read", "can't read",
    ]

    def _check(rec: Recorder) -> str | None:
        tool_names = {tc.name for tc in rec.tool_calls}
        if "web_search" in tool_names:
            return None  # honest tool use
        if not rec.replies:
            return "no reply at all"
        reply = rec.replies[-1].lower()
        if any(m in reply for m in hallucination_markers):
            return f"reply looks like hallucination of {platform} content"
        if any(d in reply for d in disclaimers):
            return None  # honest disclaimer
        if url_keyword and url_keyword.lower() in reply:
            # Acknowledged the URL — partial pass
            return None
        return (
            f"reply gave neither web_search call nor honest disclaimer; "
            f"got: {reply[:140]!r}"
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


async def run_scenario(scenario: Scenario, router, settings, test_ctx: dict) -> ScenarioResult:
    print(f"  → {scenario.name} ...", end="", flush=True)
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
    print(f" {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s)")
    return ScenarioResult(
        name=scenario.name,
        ok=ok,
        steps=step_results,
        tool_calls=list(_REC.tool_calls),
        replies=list(_REC.replies),
        elapsed_s=elapsed,
        error=error,
    )


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
        name="Reminder fire: route tới target + cc boss",
        description=(
            "Trực tiếp gọi send_reminder với target_chat_id → expect outbound tới target. "
            "Bỏ qua scheduler."
        ),
        steps=[
            # Filled in setup; placeholder.
        ],
        tags=["reminder", "fire"],
    ),
    Scenario(
        name="DM: gửi link YouTube",
        description="Boss paste link YouTube → bot phải hoặc gọi web_search, hoặc thừa nhận không xem được trực tiếp (không hallucinate nội dung video)",
        steps=[
            UserMessage("xem video này nói về gì giúp tôi: https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            Expect(
                custom=_check_link_handling("youtube"),
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
                custom=_check_link_handling("tiktok"),
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
                custom=_check_link_handling("vnexpress", url_keyword="vnexpress"),
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
        name="Escalation: task overdue → bot báo sếp",
        description="Inject task quá hạn vào Lark stub, gọi _after_deadline_check → expect DM tới assignee + report tới boss",
        steps=[
            # Filled in dynamically — needs test_ctx
        ],
        tags=["escalate", "fire"],
    ),
    Scenario(
        name="New-member event trong group đã onboarded — silent expected",
        description=(
            "Telegram emits service event 'X joined the group'. Bot không có "
            "logic auto-greet; chỉ passive identity.harvest. Test confirm: "
            "không reply, không outbound, không crash. Boss approval flow đi qua O2 (DM)."
        ),
        steps=[
            UserMessage(
                "",
                is_group=True,
                is_mentioned=False,
                new_members=[{"id": "newcomer_001", "name": "Người Mới", "username": ""}],
            ),
            Expect(
                custom=lambda rec: None if (not rec.replies and not rec.outbound) else "unexpected outbound on bare new-member event",
                no_tool_errors=True,
            ),
        ],
        tags=["onboard", "group"],
    ),
    Scenario(
        name="Approve join: boss duyệt pending member",
        description="Pre-insert pending membership → boss DM 'duyệt cho Khách Lạ' → expect approve_join + member activated",
        steps=[],  # built dynamically — needs test_ctx
        tags=["onboard", "approve"],
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
        if len(last) < 30:
            return f"reply too short: {last!r}"
        # Path A: bot actually read the file → reply references unique keyword.
        if "zulipix" in last or "qorantek" in last:
            return None
        # Path B: file format isn't supported (file_ingestion only handles
        # image/PDF/DOCX). Bot should honestly disclaim, not fabricate content.
        honest = [
            "không hỗ trợ", "chưa hỗ trợ", "không đọc",
            "chưa đọc", "không thể đọc",
        ]
        if any(h in last for h in honest):
            return None
        return (
            "reply doesn't reference unique keyword from file AND lacks "
            "an honest disclaimer about not reading it"
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
    """Pre-insert a pending membership row, then drive a boss DM to approve."""
    stranger_id = test_ctx["stranger_internal_id"]
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

    return Scenario(
        name="Approve join: boss duyệt pending member",
        description="Pre-insert pending membership → boss DM duyệt → approve_join chạy + membership active",
        steps=[
            _FireFunc(_seed),
            UserMessage(
                f"Có yêu cầu join từ Khách Lạ (chat_id={stranger_id}). Duyệt nó vào workspace của tôi với role member."
            ),
            Expect(any_tool_in={"approve_join"}, no_tool_errors=True),
            _FireFunc(_verify),
        ],
        tags=["onboard", "approve"],
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
    """Inject an overdue task into Lark stub, fire after_deadline_check."""
    boss = test_ctx["boss"]
    tasks_tbl = boss.get("lark_table_tasks") or ""
    long_conv = test_ctx["long_conv_id"]
    boss_id = test_ctx["boss_id"]

    # Deadline 2 hours in the past
    overdue_ms = int(time.time() * 1000) - 2 * 3600 * 1000

    def setup(_ctx: dict) -> None:
        # Reset and inject task
        if tasks_tbl:
            stash_lark_records(tasks_tbl, [{
                "record_id": "recOVERDUE",
                "Tên task": "Self-test overdue task",
                "Assignee": "Long",
                "Status": "Đang làm",
                "Deadline": overdue_ms,
            }])

    async def _fire_check(_step, settings) -> None:
        from src.scheduler import _after_deadline_check
        await _after_deadline_check()

    # We can't reuse FireReminder; introduce a callable step inline via custom
    return Scenario(
        name="Escalation: task overdue → bot báo sếp",
        description="_after_deadline_check trên task có Deadline < now",
        setup=setup,
        steps=[
            _FireFunc(_fire_check),
            Expect(
                custom=lambda rec: None if rec.outbound else "no outbound DM/report sent",
                no_tool_errors=True,
            ),
        ],
        tags=["escalate", "fire"],
    )


@dataclass
class _FireFunc:
    """Step that invokes an async callable(step, settings) — for custom direct-call flows."""
    fn: Callable


def _build_fire_reminder_scenario(test_ctx: dict) -> Scenario:
    """Reminder fire needs runtime test_ctx for chat ids — build dynamically."""
    boss_id = test_ctx["boss_id"]
    target = test_ctx["dm_conv_id"]
    fake_reminder = {
        "id": 999_999_999,
        "boss_chat_id": boss_id,
        "target_chat_id": target,
        "target_name": "Self-Test Target",
        "source_chat_id": test_ctx["group_conv_id"],
        "content": "Test fire — nộp báo cáo",
        "remind_at": int(time.time()),
    }
    return Scenario(
        name="Reminder fire: route tới target + cc boss",
        description="Fire send_reminder() trực tiếp",
        steps=[
            FireReminder(reminder=fake_reminder),
            Expect(outbound_to=target),
        ],
        tags=["reminder", "fire"],
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
        "Reminder fire: route tới target + cc boss": _build_fire_reminder_scenario,
        "DM: gửi file đính kèm": _build_file_scenario,
        "Escalation: task overdue → bot báo sếp": _build_escalate_scenario,
        "Approve join: boss duyệt pending member": _build_approve_join_scenario,
        "Image attachment: bot nhận diện ảnh": _build_image_scenario,
        "Reminder fire: source-only (không target) → vào source group": _build_source_only_reminder_scenario,
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

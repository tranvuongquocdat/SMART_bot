# Phase 4b-1 — Agent Package + Dispatcher Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the `src/agent/` package structure that Phase 4b-2 will populate. Move OpenAI tool schemas to a pure-data module. Build `ToolHandler` base + `ToolDispatcher` registry. Migrate 2 simple tools (`web_search`, `escalate_to_advisor`) as a pattern proof-of-concept; the dispatcher transparently falls back to the legacy `tools.execute_tool` for the other ~48 tools, so end-to-end behaviour is unchanged.

**Architecture:** `agent/tool_definitions.py` holds OpenAI schemas — pure data, no logic. `agent/handlers/_base.py` defines a `ToolHandler` Protocol (one method: `handle(args, ctx) -> str`). `agent/tool_dispatcher.py` is a registry that maps name → handler instance; on unknown name it delegates to the legacy dispatcher. `agent/handlers/web_search.py` and `agent/handlers/escalate.py` ship as the first two handlers — both wrap existing function calls. `src/agent.py` wires the new dispatcher; legacy `tools/__init__.execute_tool` stays as the fallback.

**Tech Stack:** Python 3.11+, pytest with `asyncio_mode = auto`.

**Spec reference:** [docs/superpowers/specs/2026-04-28-platform-channel-and-layered-architecture-design.md](../specs/2026-04-28-platform-channel-and-layered-architecture-design.md), Phase 4 — the **dispatcher / handler / tool_definitions** sub-set. Service layer + agent classes deferred to 4b-2 / 4b-3.

---

## Scope Notes

**In scope:**

- `src/agent/__init__.py` (empty package marker — `agent.py` keeps living next to it as a module).
- `src/agent/tool_definitions.py` — copy-paste of `tools/__init__.TOOL_DEFINITIONS` (data only, no imports of tools/logic). `tools/__init__` re-exports for backward compat.
- `src/agent/handlers/__init__.py` + `agent/handlers/_base.py` — `ToolHandler` Protocol-style base class.
- `src/agent/tool_dispatcher.py` — `ToolDispatcher` class with `execute(name, args, ctx) -> str`, registry over handlers, transparent fallback to legacy.
- `src/agent/handlers/web_search.py` and `src/agent/handlers/escalate.py` — first 2 handlers (low-blast-radius, no DB writes).
- Wire `src/agent.py` to construct `ToolDispatcher` once at module load and call `dispatcher.execute(...)` instead of `tools.execute_tool(...)`.
- Tests for the dispatcher: handler hit, fallback path, error formatting.
- Smoke: boot bot, DM "tìm tin tức về AI" (triggers `web_search` → handler path), confirm reply works.

**Out of scope (Phase 4b-2):**

- The other ~48 tool handlers — Phase 4b-2 mass-migrates.
- Service layer (`services/task_service.py`, etc.) — Phase 4b-2.
- Agent classes (`secretary_agent.py`, `reminder_agent.py`, `advisor_agent.py`, `onboarding_agent.py`) — Phase 4b-3.
- `LLMClient` migration (callers still use legacy `infrastructure.openai_client`) — Phase 4b-3.
- Deletion of `tools/` folder — happens at end of Phase 4b-2 once no callers remain.

---

## File Structure After This Phase

```
src/
├── agent.py                       # MODIFIED — uses ToolDispatcher
├── agent/                         # NEW package (sibling to agent.py)
│   ├── __init__.py
│   ├── tool_definitions.py        # OpenAI tool schema (pure data)
│   ├── tool_dispatcher.py         # ToolDispatcher registry
│   └── handlers/
│       ├── __init__.py
│       ├── _base.py               # ToolHandler base class
│       ├── web_search.py
│       └── escalate.py
└── tools/
    └── __init__.py                # MODIFIED — re-exports TOOL_DEFINITIONS from new home

tests/unit/
└── test_tool_dispatcher.py        # NEW
```

**`agent.py` vs `agent/`:** Python allows both a module and package with the same name only if the package wins; we keep `agent.py` as-is for now (it has the LLM loop). The `agent/` package coexists as a sibling — imports work because Python's import system picks one or the other based on `sys.path` lookup. Since `agent.py` exists and is imported as `src.agent`, we keep `src.agent` referring to the module. The new package is `src.agent` too — **conflict.** Resolve by renaming the package import path to `src.agent_pkg` for now; or alternatively, *move* `agent.py` into `agent/__init__.py`. The latter is cleaner but Phase 4b-3 reorganises `agent.py` anyway. **Decision:** rename the new package to `src.agent_pkg` for Phase 4b-1; Phase 4b-3 collapses `agent.py` into `agent/__init__.py` and renames `agent_pkg` → `agent`. This avoids touching `agent.py` import paths today while `agent.py` is still the single entry point for the LLM loop.

Updated structure:

```
src/
├── agent.py                       # MODIFIED — uses ToolDispatcher
├── agent_pkg/                     # NEW (renamed in 4b-3 → agent/)
│   ├── __init__.py
│   ├── tool_definitions.py
│   ├── tool_dispatcher.py
│   └── handlers/
│       ├── __init__.py
│       ├── _base.py
│       ├── web_search.py
│       └── escalate.py
```

---

## Task 1 — Create `agent_pkg/` package + move `TOOL_DEFINITIONS`

**Files:**
- Create: `src/agent_pkg/__init__.py`
- Create: `src/agent_pkg/tool_definitions.py`
- Modify: `src/tools/__init__.py` — replace literal list with re-export.

- [ ] **Step 1: Create the package init**

Create `src/agent_pkg/__init__.py` (empty):

```python
```

- [ ] **Step 2: Copy TOOL_DEFINITIONS to the new module**

Read the literal `TOOL_DEFINITIONS = [...]` block from `src/tools/__init__.py` (it spans roughly lines 28–1140). Copy the exact list contents into a new file `src/agent_pkg/tool_definitions.py`:

```python
"""OpenAI tool schemas — pure data, no logic, no imports of tool functions.

Phase 4b-2 will add new entries (or move them) as tools are migrated to
handler classes. Phase 4b-3 will rename this module to `agent/tool_definitions.py`.
"""
from __future__ import annotations


TOOL_DEFINITIONS: list[dict] = [
    # ... the entire list copied verbatim from tools/__init__.py ...
]
```

The list is large (~1100 lines). Use a single bulk copy/paste; do not edit the contents. The diff for this task should be:
- New file `src/agent_pkg/tool_definitions.py` containing the full list.
- `src/tools/__init__.py` replaces its literal list with a re-import:

```python
# Re-export from agent_pkg so legacy callers keep working until 4b-3.
from src.agent_pkg.tool_definitions import TOOL_DEFINITIONS  # noqa: F401
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.agent_pkg.tool_definitions import TOOL_DEFINITIONS; print(len(TOOL_DEFINITIONS))"
```

Expected: an integer (currently 50+ tools).

```bash
uv run python -c "from src.tools import TOOL_DEFINITIONS as a; from src.agent_pkg.tool_definitions import TOOL_DEFINITIONS as b; assert a is b; print('aliased OK')"
```

Expected: `aliased OK`.

- [ ] **Step 4: Commit**

```bash
git add src/agent_pkg/__init__.py src/agent_pkg/tool_definitions.py src/tools/__init__.py
git commit -m "refactor(agent): move TOOL_DEFINITIONS to agent_pkg/tool_definitions.py (data only)"
```

---

## Task 2 — `agent_pkg/handlers/_base.py` — `ToolHandler` base

**Files:**
- Create: `src/agent_pkg/handlers/__init__.py`
- Create: `src/agent_pkg/handlers/_base.py`

- [ ] **Step 1: Empty package init**

Create `src/agent_pkg/handlers/__init__.py` (empty):

```python
```

- [ ] **Step 2: Define the base**

Create `src/agent_pkg/handlers/_base.py`:

```python
"""ToolHandler base — every LLM-facing tool implements this Protocol.

Phase 4b-2 services + handlers concrete patterns. The base intentionally
keeps the contract minimal so handlers can vary in how they parse args /
format errors / inject services.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.context import ChatContext


@runtime_checkable
class ToolHandler(Protocol):
    """A single LLM-facing tool. The dispatcher resolves by `name`."""

    name: str

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        """Execute the tool. Returns string for the LLM to read.

        Conventions for the returned string:
        - Success: human-readable summary, e.g., `"Đã tạo task 'foo'."`.
        - Recoverable failure: `[TOOL_ERROR:<code>] <reason>` so the LLM
          can decide a fallback. The dispatcher wraps unhandled exceptions
          in `[TOOL_ERROR:unknown]` automatically.
        """
        ...
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.agent_pkg.handlers._base import ToolHandler; print(ToolHandler)"
```

Expected: prints the class.

- [ ] **Step 4: Commit**

```bash
git add src/agent_pkg/handlers/__init__.py src/agent_pkg/handlers/_base.py
git commit -m "feat(agent_pkg/handlers): add ToolHandler Protocol base"
```

---

## Task 3 — `agent_pkg/tool_dispatcher.py` — registry + legacy fallback

**Files:**
- Create: `src/agent_pkg/tool_dispatcher.py`

- [ ] **Step 1: Implement `ToolDispatcher`**

Create `src/agent_pkg/tool_dispatcher.py`:

```python
"""ToolDispatcher — name → handler registry with legacy fallback.

For Phase 4b-1 only a handful of handlers are migrated. Unknown names
delegate to `src.tools.execute_tool` (the legacy `match`-statement
dispatcher) so the bot keeps working end-to-end. Phase 4b-2 mass-migrates
the rest; once every tool has a handler, the fallback can be removed and
`src.tools` deleted entirely (Phase 4b-2 done criterion).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext

logger = logging.getLogger("agent.dispatcher")


class ToolDispatcher:
    def __init__(self, handlers: list[ToolHandler]) -> None:
        self._by_name: dict[str, ToolHandler] = {}
        for h in handlers:
            if h.name in self._by_name:
                raise ValueError(f"duplicate handler name: {h.name!r}")
            self._by_name[h.name] = h

    @property
    def known_names(self) -> set[str]:
        return set(self._by_name.keys())

    async def execute(
        self, name: str, arguments: str | dict, ctx: ChatContext,
    ) -> str:
        handler = self._by_name.get(name)
        if handler is None:
            return await self._fallback(name, arguments, ctx)

        try:
            args = self._parse_args(arguments)
        except json.JSONDecodeError as e:
            logger.warning("Bad JSON args for %s: %s", name, e)
            return f"[TOOL_ERROR:bad_args] {name}: invalid JSON"

        try:
            return await handler.handle(args, ctx)
        except Exception as exc:  # noqa: BLE001  — uniform error envelope
            err_type = type(exc).__name__
            return f"[TOOL_ERROR:unknown] {name} failed ({err_type}): {exc}"

    @staticmethod
    def _parse_args(arguments: str | dict) -> dict:
        if isinstance(arguments, dict):
            return arguments
        return json.loads(arguments)

    @staticmethod
    async def _fallback(name: str, arguments: str | dict, ctx: ChatContext) -> str:
        # Keep the import inside the method so unit tests can run without
        # importing the heavy legacy tools module.
        from src.tools import execute_tool as _legacy_execute
        return await _legacy_execute(name, arguments, ctx)
```

- [ ] **Step 2: Boot-check**

```bash
uv run python -c "from src.agent_pkg.tool_dispatcher import ToolDispatcher; d = ToolDispatcher([]); print(d.known_names)"
```

Expected: `set()`.

- [ ] **Step 3: Commit**

```bash
git add src/agent_pkg/tool_dispatcher.py
git commit -m "feat(agent_pkg): add ToolDispatcher with legacy fallback"
```

---

## Task 4 — Two example handlers (`web_search`, `escalate_to_advisor`)

**Files:**
- Create: `src/agent_pkg/handlers/web_search.py`
- Create: `src/agent_pkg/handlers/escalate.py`

> Why these two? `web_search` is a pure function call (no DB, no LLM), proving the simple wrapper pattern. `escalate_to_advisor` returns a sentinel string read by `agent.py` to switch agents — proves the dispatcher correctly preserves return-string semantics.

- [ ] **Step 1: `web_search` handler**

Inspect the existing tool. Run:

```bash
grep -n "async def web_search" src/tools/web_search.py
```

The legacy function has signature `async def web_search(query: str) -> str:` (or similar — the schema in `TOOL_DEFINITIONS` lists `query` as required). Inspect to confirm the exact arg list.

Create `src/agent_pkg/handlers/web_search.py`:

```python
"""web_search handler — wraps `src.tools.web_search.web_search`.

Phase 4b-2 migrates the underlying function to a `WebSearchService`; for
4b-1 we wrap the existing function so the dispatcher pattern is exercised.
"""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import web_search as _legacy


class WebSearchHandler(ToolHandler):
    name = "web_search"

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        query = args.get("query", "")
        if not query:
            return "[TOOL_ERROR:bad_args] web_search: missing 'query'"
        return await _legacy.web_search(query=query)
```

- [ ] **Step 2: `escalate_to_advisor` handler**

The legacy dispatch (line 1257 in `tools/__init__.py`) returns the sentinel `"__ESCALATE__"` directly — no underlying function. Replicate verbatim.

Create `src/agent_pkg/handlers/escalate.py`:

```python
"""escalate_to_advisor handler — returns the sentinel `__ESCALATE__`.

`agent.py` reads this string to switch the LLM loop to the advisor agent.
The handler holds no logic; the sentinel is part of the agent contract.
"""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext


class EscalateToAdvisorHandler(ToolHandler):
    name = "escalate_to_advisor"

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return "__ESCALATE__"
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "
from src.agent_pkg.handlers.web_search import WebSearchHandler
from src.agent_pkg.handlers.escalate import EscalateToAdvisorHandler
print(WebSearchHandler.name, EscalateToAdvisorHandler.name)
"
```

Expected: `web_search escalate_to_advisor`.

- [ ] **Step 4: Commit**

```bash
git add src/agent_pkg/handlers/web_search.py src/agent_pkg/handlers/escalate.py
git commit -m "feat(agent_pkg/handlers): add WebSearch + EscalateToAdvisor handlers"
```

---

## Task 5 — Unit test the dispatcher

**Files:**
- Create: `tests/unit/test_tool_dispatcher.py`

- [ ] **Step 1: Write the test**

Create `tests/unit/test_tool_dispatcher.py`:

```python
"""Tests for ToolDispatcher — registry hit, fallback path, error envelopes."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.agent_pkg.handlers._base import ToolHandler
from src.agent_pkg.tool_dispatcher import ToolDispatcher
from src.context import ChatContext


def _ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="u1", sender_name="x", sender_type="boss",
        boss_chat_id="b1", boss_name="b",
        lark_base_token="", lark_table_people="", lark_table_tasks="",
        lark_table_projects="", lark_table_ideas="",
        lark_table_reminders="", lark_table_notes="",
        chat_id="c1", is_group=False, group_name="",
        messages_collection="m_b1_1536", tasks_collection="t_b1_1536",
        all_memberships=[],
    )


@dataclass
class _Fake:
    name: str
    return_value: str

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return self.return_value


@pytest.mark.asyncio
async def test_known_name_invokes_handler():
    d = ToolDispatcher([_Fake(name="t1", return_value="ok")])
    out = await d.execute("t1", {}, _ctx())
    assert out == "ok"


@pytest.mark.asyncio
async def test_unknown_name_falls_back_to_legacy(monkeypatch):
    # Stub the legacy entry-point so we can assert it was called without
    # importing the real (heavy) tools chain.
    captured: dict = {}

    async def _fake_legacy(name, arguments, ctx):
        captured["name"] = name
        captured["arguments"] = arguments
        return "from-legacy"

    import src.tools as _tools
    monkeypatch.setattr(_tools, "execute_tool", _fake_legacy)

    d = ToolDispatcher([])
    out = await d.execute("unknown_tool", {"x": 1}, _ctx())
    assert out == "from-legacy"
    assert captured["name"] == "unknown_tool"
    assert captured["arguments"] == {"x": 1}


@pytest.mark.asyncio
async def test_handler_exception_wrapped():
    class _Boom:
        name = "boom"
        async def handle(self, args, ctx):
            raise RuntimeError("kaboom")

    d = ToolDispatcher([_Boom()])
    out = await d.execute("boom", {}, _ctx())
    assert out.startswith("[TOOL_ERROR:unknown]")
    assert "kaboom" in out


@pytest.mark.asyncio
async def test_bad_json_args_returns_error():
    d = ToolDispatcher([_Fake(name="t1", return_value="ok")])
    out = await d.execute("t1", "not-json{", _ctx())
    assert "[TOOL_ERROR:bad_args]" in out


def test_duplicate_handler_name_raises():
    a = _Fake(name="dup", return_value="a")
    b = _Fake(name="dup", return_value="b")
    with pytest.raises(ValueError, match="duplicate handler name"):
        ToolDispatcher([a, b])
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/unit/test_tool_dispatcher.py -v
```

Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tool_dispatcher.py
git commit -m "test(agent_pkg/dispatcher): registry hit, fallback, error envelopes"
```

---

## Task 6 — Wire the dispatcher into `src/agent.py`

**Files:**
- Modify: `src/agent.py` — replace `tools.execute_tool(...)` calls with `_dispatcher.execute(...)`.

- [ ] **Step 1: Find call sites**

```bash
grep -n "tools\.execute_tool\|execute_tool(" src/agent.py
```

There should be one or two sites where the LLM loop runs each tool call.

- [ ] **Step 2: Add dispatcher construction at module top**

Add to the import block at the top of `src/agent.py`:

```python
from src.agent_pkg.tool_dispatcher import ToolDispatcher
from src.agent_pkg.handlers.web_search import WebSearchHandler
from src.agent_pkg.handlers.escalate import EscalateToAdvisorHandler
```

After all imports, before the first function definition, add:

```python
# Phase 4b-1: ToolDispatcher with two migrated handlers; falls back to
# `src.tools.execute_tool` for the rest. Phase 4b-2 mass-migrates the
# remaining tools and removes the fallback.
_dispatcher = ToolDispatcher([
    WebSearchHandler(),
    EscalateToAdvisorHandler(),
])
```

- [ ] **Step 3: Swap the call site(s)**

For each match found in Step 1, replace:

```python
result = await tools.execute_tool(name, arguments, ctx)
```

with:

```python
result = await _dispatcher.execute(name, arguments, ctx)
```

(The dispatcher's signature matches `execute_tool(name, arguments, ctx)` exactly.)

- [ ] **Step 4: Boot-check**

```bash
uv run python -c "import src.main; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Run all unit tests**

```bash
uv run pytest tests/unit/ --ignore=tests/unit/test_context.py 2>&1 | tail -10
```

Expected: every test passes.

- [ ] **Step 6: Commit**

```bash
git add src/agent.py
git commit -m "feat(agent): route tool calls through ToolDispatcher (legacy fallback)"
```

---

## Task 7 — Manual smoke test

**Files:** None.

- [ ] **Step 1: Boot the bot**

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Expected: `Application startup complete`, `Polling started`.

- [ ] **Step 2: DM "hello"**

DM the bot: `hello`. Expected: bot replies normally. Most tools the LLM might call go through the legacy fallback — must work end-to-end.

- [ ] **Step 3: DM a `web_search` query**

DM: `tìm tin tức gần đây về AI`. The LLM should call `web_search`, which now flows through `WebSearchHandler` instead of the legacy match-case.

Watch the server log for any traceback originating in `src/agent_pkg/`. Bot should reply with search results (or graceful fallback if API limits hit — just no traceback from our dispatcher).

- [ ] **Step 4: Stop the bot**

`Ctrl-C`.

- [ ] **Step 5: Final state check**

```bash
git log --oneline | head -10
git status
```

Expected: ~6 commits; clean tree.

---

## Done Criteria

- [ ] `src/agent_pkg/` exists with `tool_definitions.py`, `tool_dispatcher.py`, `handlers/_base.py`, `handlers/web_search.py`, `handlers/escalate.py`.
- [ ] `src/tools/__init__.py` re-exports `TOOL_DEFINITIONS` from the new home (no duplicated literal).
- [ ] `src/agent.py` calls `_dispatcher.execute(...)` instead of `tools.execute_tool(...)`.
- [ ] `python -c "import src.main"` succeeds.
- [ ] `pytest tests/unit/test_tool_dispatcher.py -v` is green.
- [ ] Manual smoke (Task 7): DM "hello" works (legacy path), DM a `web_search` query works (handler path).
- [ ] Legacy `tools/__init__.execute_tool` is unchanged — Phase 4b-2 will start hollowing it as handlers migrate.

When all checked, Phase 4b-1 is done. Next: Phase 4b-2 mass-migrates services + remaining ~48 handlers + deletes `tools/`.

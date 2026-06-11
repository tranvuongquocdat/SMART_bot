"""Plugin loader integration: a fixture plugin tree is created in tmp_path,
``load_all`` is invoked against it, and we verify:

  - manifest is parsed and the plugin name reported.
  - ``plugins.<name>.tools`` is imported and the @tool decorator side-effect
    registered the tool into the shared tool registry.
  - missing/broken plugin is skipped (loader never raises).
  - per-boss filter in agent_loop._allowed_tools adds enabled plugin tools.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.plugins_loader import load_all
from src.tools.registry import _REGISTRY


def _write_plugin(
    base: Path,
    name: str,
    *,
    manifest_extra: str = "",
    tool_name: str | None = None,
) -> None:
    pdir = base / name
    pdir.mkdir(parents=True)
    (pdir / "__init__.py").write_text("")
    (pdir / "manifest.toml").write_text(
        textwrap.dedent(
            f"""
            name = "{name}"
            version = "0.0.1"
            {manifest_extra}
            """
        )
    )
    tname = tool_name or f"{name}_ping"
    (pdir / "tools.py").write_text(
        textwrap.dedent(
            f"""
            from src.plugin_api import tool, ToolContext, ToolResult

            @tool(
                name="{tname}",
                description="ping from fixture plugin",
                parameters={{"type":"object","properties":{{}}}},
            )
            async def ping(ctx: ToolContext) -> ToolResult:
                return ToolResult(content="pong")
            """
        )
    )


@pytest.fixture(autouse=True)
def _isolate_sys_path():
    """Restore sys.path after each test so a tmp plugins dir doesn't leak."""
    snapshot = list(sys.path)
    snapshot_mods = set(sys.modules.keys())
    yield
    sys.path[:] = snapshot
    # purge any plugin modules we imported
    for m in list(sys.modules.keys()):
        if m not in snapshot_mods and (
            m.startswith("plugins") or "plugins." in m
        ):
            sys.modules.pop(m, None)


def test_load_all_empty_dir_returns_empty(tmp_path: Path):
    pdir = tmp_path / "plugins_empty"
    pdir.mkdir()
    assert load_all(pdir) == []


def test_load_all_missing_dir_returns_empty(tmp_path: Path):
    assert load_all(tmp_path / "does_not_exist") == []


def test_load_all_registers_tools(tmp_path: Path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    _write_plugin(pdir, "demoplug", tool_name="demoplug_hello")

    loaded = load_all(pdir)
    assert "demoplug" in loaded
    assert "demoplug_hello" in _REGISTRY
    td = _REGISTRY["demoplug_hello"]
    assert td.description == "ping from fixture plugin"


def test_load_all_skips_broken_plugin(tmp_path: Path, caplog):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    bad = pdir / "broken"
    bad.mkdir()
    (bad / "__init__.py").write_text("")
    (bad / "manifest.toml").write_text('name = "broken"\n')
    (bad / "tools.py").write_text("raise RuntimeError('nope')\n")
    # And a healthy one alongside it
    _write_plugin(pdir, "okplug", tool_name="okplug_works")

    loaded = load_all(pdir)
    assert "okplug" in loaded
    assert "broken" not in loaded
    assert "okplug_works" in _REGISTRY


def test_load_all_skips_dirs_without_manifest(tmp_path: Path):
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    (pdir / "no_manifest").mkdir()
    (pdir / "no_manifest" / "__init__.py").write_text("")
    assert load_all(pdir) == []


@pytest.mark.asyncio
async def test_allowed_tools_includes_enabled_plugin_tools(
    db_pool, boss_user, tmp_path: Path
):
    """When boss_integrations.enabled=TRUE for plugin_id 'demoplug',
    agent_loop._allowed_tools must include the plugin's namespaced tool."""
    from src.agents.agent_loop import _allowed_tools

    # Register a tool whose prefix matches the enabled plugin_id.
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    _write_plugin(pdir, "demoplug", tool_name="demoplug_action")
    load_all(pdir)
    assert "demoplug_action" in _REGISTRY

    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO boss_integrations (boss_id, plugin_id, enabled)
            VALUES ($1,'demoplug',TRUE)
            ON CONFLICT (boss_id, plugin_id) DO UPDATE SET enabled=TRUE
            """,
            boss_user["id"],
        )
        # Allowlist names must also be active per-boss (strict intersect).
        await c.execute(
            "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, 'core_search') "
            "ON CONFLICT DO NOTHING",
            boss_user["id"],
        )

    cfg = SimpleNamespace(tools={"core_search"})
    ctx = SimpleNamespace(
        db=db_pool,
        boss=SimpleNamespace(id=boss_user["id"]),
    )
    allowed = await _allowed_tools(cfg, ctx)
    assert "core_search" in allowed
    assert "demoplug_action" in allowed


@pytest.mark.asyncio
async def test_allowed_tools_excludes_disabled_plugin(db_pool, boss_user):
    """Disabled plugins must not contribute to the allowlist."""
    from src.agents.agent_loop import _allowed_tools

    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO boss_integrations (boss_id, plugin_id, enabled)
            VALUES ($1,'demoplug',FALSE)
            ON CONFLICT (boss_id, plugin_id) DO UPDATE SET enabled=FALSE
            """,
            boss_user["id"],
        )
    cfg = SimpleNamespace(tools={"core_search"})
    ctx = SimpleNamespace(
        db=db_pool,
        boss=SimpleNamespace(id=boss_user["id"]),
    )
    allowed = await _allowed_tools(cfg, ctx)
    # Even if demoplug_action is in registry from prior test, it should
    # not appear because the boss_integrations row says enabled=FALSE.
    assert "demoplug_action" not in allowed

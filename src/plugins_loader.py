"""Plugin loader — scan ``plugins/<name>/manifest.toml`` and import tools.

This is the MVP scaffold: every directory under ``PLUGINS_DIR`` with a
``manifest.toml`` is considered a plugin. We try to import
``plugins.<name>.tools``; the import's side effect (``@tool`` decorators)
registers tools into the shared `_REGISTRY` in ``src.tools.registry``.

Per-boss enablement is handled at the agent_loop tool-filter layer
against ``boss_integrations`` rows; this loader only ensures the tools
are *importable*. A missing or broken plugin logs and is skipped — never
fatal at startup.

For test isolation, callers can override ``PLUGINS_DIR`` by passing
``plugins_dir=`` to :func:`load_all`.
"""

from __future__ import annotations

import importlib
import logging
import sys
import tomllib
from pathlib import Path

log = logging.getLogger(__name__)

# Repo-root/plugins/<name>/manifest.toml
PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


def load_all(plugins_dir: Path | None = None) -> list[str]:
    """Import every plugin under ``plugins_dir`` (default PLUGINS_DIR).

    Returns the list of plugin names successfully loaded. Failures are
    logged with ``logger.exception`` but never raised — a broken plugin
    must not bring down the app.
    """
    base = plugins_dir or PLUGINS_DIR
    registered: list[str] = []
    if not base.exists():
        return registered

    # Make sure ``plugins`` is importable as a top-level package even when
    # the loader is called from inside a sub-package context.
    parent = str(base.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        manifest_path = p / "manifest.toml"
        if not manifest_path.exists():
            continue
        try:
            manifest = tomllib.loads(manifest_path.read_text())
        except Exception:
            log.exception("plugin manifest parse failed plugin=%s", p.name)
            continue
        name = manifest.get("name") or p.name
        module = f"{base.name}.{p.name}.tools"
        try:
            importlib.import_module(module)
            log.info(
                "plugin loaded plugin=%s tools=%s",
                name,
                manifest.get("capabilities", {}).get("tools", []),
            )
            registered.append(name)
        except Exception:
            log.exception("plugin load failed plugin=%s", name)
    return registered

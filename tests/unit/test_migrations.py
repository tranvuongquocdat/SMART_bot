"""Guard tests for the Alembic migration chain.

Static, fast, no DB. Catch the two failure modes that have bitten us:

1. **Multiple heads** — two parallel branches each add the next ``00NN``
   migration revising the same ``down_revision`` → divergent heads that explode
   the moment they meet on ``alembic upgrade head``.
2. **Broken / dangling chain** — a revision referenced as ``down_revision`` that
   isn't resolvable (e.g. ``0014`` was left untracked while ``0015+`` depended on
   it → fine locally, broken on a clean clone), or an on-disk file not wired into
   the chain.

The git-hygiene side (a migration file that exists locally but was never
committed) is guarded separately by ``scripts/git-hooks/pre-push`` — a test on a
machine where the file is physically present cannot see that it's uncommitted.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = str(_REPO_ROOT / "alembic.ini")
_VERSIONS_DIR = _REPO_ROOT / "migrations" / "versions"


def _script_dir() -> ScriptDirectory:
    # %(here)s in alembic.ini resolves to the ini's directory, so an absolute
    # path makes this independent of the working directory pytest runs from.
    return ScriptDirectory.from_config(Config(_ALEMBIC_INI))


def test_single_head() -> None:
    """Exactly one head. More than one = an unresolved branch/merge conflict."""
    heads = _script_dir().get_heads()
    assert len(heads) == 1, (
        f"Expected exactly 1 migration head, found {len(heads)}: {heads}.\n"
        "Two branches added migrations off the same parent. Resolve with:\n"
        f"  uv run alembic merge -m 'merge heads' {' '.join(heads)}"
    )


def test_chain_resolves_and_covers_every_file() -> None:
    """Walking from head to base must resolve every revision (raises on a
    dangling ``down_revision``) and reach every ``NNNN_*.py`` on disk (catches an
    orphan file or a duplicate/typo'd revision id)."""
    script = _script_dir()
    walked = {rev.revision for rev in script.walk_revisions()}
    on_disk = {p.name.split("_", 1)[0] for p in _VERSIONS_DIR.glob("[0-9]*.py")}

    missing = on_disk - walked
    assert not missing, (
        f"Migration files on disk but not in the chain: {sorted(missing)}. "
        "Likely a bad/typo'd down_revision link, a duplicate revision id, or an "
        "orphan file. Every NNNN_*.py must be reachable from the single head."
    )


def test_revision_id_matches_filename_number() -> None:
    """Convention: ``0007_plan_pricing.py`` must declare ``revision = "0007"``.
    Keeps the sequential scheme honest so ``scripts/new_migration.sh`` and humans
    can trust the filename number == revision id."""
    script = _script_dir()
    mismatches = []
    for rev in script.walk_revisions():
        # rev.module.__file__ is the path of the migration file
        fname = Path(rev.module.__file__).name
        file_num = fname.split("_", 1)[0]
        if file_num != rev.revision:
            mismatches.append(f"{fname}: revision={rev.revision!r} but filename says {file_num!r}")
    assert not mismatches, "Filename number != revision id:\n  " + "\n  ".join(mismatches)

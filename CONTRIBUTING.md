# Contributing

Onboarding map for engineers joining the codebase. This is the *how to work
here* guide — for *why the architecture is shaped this way* (decision log +
BUILD LOG), read [`docs/architecture/system-design.md`](docs/architecture/system-design.md).

The product in one line: a virtual secretary bot that is added to group chats to
record and support work. Group-first; per-boss multi-tenant.

---

## Quick start

Full setup is in the [README](README.md#chạy-local-uv). The short version:

```bash
docker compose -f docker/docker-compose.yml up -d        # Postgres:5433 + Qdrant:6333
uv sync --extra dev                                      # deps INCLUDING test/lint
uv run alembic upgrade head
git config core.hooksPath scripts/git-hooks              # enable quality gates (once)
uv run pytest tests/unit tests/integration -q            # baseline: 494 passed, 4 skipped
```

> Tests need the `--extra dev` sync **and** Docker up. `uv run pytest` (not bare
> `pytest`, which hits a broken system Python). See [README](README.md).

---

## Architecture

Backend is layered; dependencies point downward (entrypoints → orchestration →
data/IO → domain). Don't reach upward (a repository must not import a service).

| Layer | Dir | Responsibility |
|-------|-----|----------------|
| Entrypoints | `web/`, `channels/`, `scheduler/` | FastAPI routes; chat-channel adapters; APScheduler jobs |
| Orchestration | `services/`, `agents/` | Business logic; the LLM agent loop + responders + operations/triggers |
| Capabilities | `tools/`, `retrieval/`, `memory/`, `llm/`, `media/` | `@tool`s the agent calls; RAG pipeline; memory/knowledge index; LLM clients+gateway; URL/media extraction |
| Data / domain | `repositories/`, `domain/`, `infra/` | DB access (asyncpg); pure domain dataclasses; db pool, metrics, qdrant |
| Cross-cutting | `events/`, `security/` | in-process event bus; rate limiting + cost caps |

Inbound from every channel flows through **`InboundIngest`** (one wrapper, with
boss-spoke gating). The web test channel's `/chat/send` is the one intentional
exception.

---

## Conventions that matter (please follow)

**1. Boss-scoping is a security boundary, not a style choice.**
Every repository extends `BossScopedRepo` (`repositories/base.py`) and **must
filter every query by `self.ctx.boss_id`** — unless the op is explicitly
superadmin-only, in which case assert the role. Cross-boss data leakage is the
worst bug we can ship. Repos convert rows via a `_row_to_<model>()` helper.

**2. Language policy — code is English, the product is Vietnamese.**
- Identifiers, docstrings, comments: **English.**
- Bot prompts, user-facing replies, seed/product strings: **Vietnamese** (that's
  data, not code — never "translate" it).
- *Legacy note:* some older modules still carry Vietnamese comments; they're being
  migrated. New/changed code should be English.

**3. User-facing strings are localized, never hard-coded.**
- Backend: `tr(ctx, vi="…", en="…")` (`web/i18n.py`) — picks by `ctx.ui_language`.
- Frontend: `useT()` with `vi`/`en` parity in `frontend/src/locales/`.

**4. Agent tools register via `@tool`.**
`@tool(name=, feature=, cost_class=, available_to={...}, parallel_safe=)`
(`tools/registry.py`). Core tools are always-on for every boss. Tool modules are
force-imported in `tools/__init__.py` so the decorator runs at startup.

**5. LLM calls use `max_completion_tokens`, not `max_tokens`.**
Newer OpenAI models reject the legacy param; Groq + gpt-4o accept the new one.

---

## Workflow

**Migrations** — never hand-pick a revision number:
```bash
scripts/new_migration.sh "short description"   # auto-numbers off the current head
```
Sequential `NNNN_*.py`, single linear chain. `tests/unit/test_migrations.py`
enforces exactly one head + an unbroken chain. Commit the new file in the **same
commit** as the code that needs it (an uncommitted migration breaks fresh clones).

**Quality gates** (git hooks, enabled via `core.hooksPath`):

| Hook | Blocks on |
|------|-----------|
| `pre-commit` | `ruff` errors in the **staged** Python files |
| `pre-push` | an untracked migration; or **failing tests** (only when the DB is up — skipped with a warning otherwise) |

Bypass in emergencies with `--no-verify`.

**Tests** — every Q&A/behavior bug becomes a gold case
(`scripts/gold_cases.json` + `scripts/harness.py gold`). Integration tests run
against a throwaway `*_test` DB, auto-bootstrapped by `tests/conftest.py`.

**Types** — `mypy` is configured `strict`. We're moving to a green baseline
incrementally (override third-party stubs → fix real type errors → tighten
per-module), then it joins the gate. Don't add new untyped public functions.

**Lint/format** — `ruff` (line length 100, target py312).

---

## Pull / commit hygiene

- Keep commits focused and atomic; write *why* in the body, not just *what*.
- Run the suite locally before pushing (the pre-push gate does this for you).
- Don't bundle unrelated mechanical churn with a behavior change.

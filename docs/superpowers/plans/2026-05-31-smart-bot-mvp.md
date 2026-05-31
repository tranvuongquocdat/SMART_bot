# SMART_bot MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build group-note bot cho sếp SME Việt Nam dùng Zalo personal account; ghi message, duy trì 1 markdown note/group, trả lời Q&A trong group + DM, đặt reminder. Web admin dual-mode bot account (platform pool + boss-owned).

**Architecture:** Event-driven EventBus (in-process pub/sub), capability-bundle operations (declarative `@operation` decorator), declarative registries cho tool/memory/retrieval/llm/trigger/media/resolver. 1 vector DB (Qdrant) + Postgres (FTS + structured). FastAPI + HTMX + Tailwind web. Node bridge (zca-js) cho Zalo personal.

**Tech Stack:** Python 3.12+, FastAPI, asyncpg, Qdrant 1.x, Alembic, structlog, pytest, APScheduler, HTMX + Tailwind + Jinja2, Node 24 + zca-js, OpenAI + Groq + Gemini (KHÔNG Claude — xem memory `project-no-claude-models`).

**Spec reference:** `docs/superpowers/specs/2026-05-30-group-note-bot/` (15 sections, pass 4). Plan này map task → section spec; subagent thực hiện task đọc spec section tương ứng.

---

## Cách đọc plan

- **Task 0** = spike Zalo, BLOCK toàn bộ Batch E (channel-related).
- **Batch A** (Foundation) phải xong trước Batch B/C/D/E/F/G.
- **Batch B + C + E** có thể parallel sau khi Batch A xong.
- **Batch D** depends Batch C.
- **Batch G** (Web) depends Batch A (auth) + Batch B (token_usage) — có thể parallel với Batch C/D.
- **Batch H** (Polish) depends mọi batch trước.
- **Final** = E2E, sau cùng.

Mỗi task có:
- **Depends on**: task phải xong trước
- **Parallel-safe with**: task có thể chạy đồng thời
- **Files**: Create / Modify / Test (exact path)
- **Acceptance**: tiêu chí pass observable
- **Steps**: TDD checklist, code đầy đủ

Task **"pattern-introducing"** (first repo, first op, first tool, first stage, first adapter) — full TDD per-step. Task **"pattern-following"** — tight, show key code khác biệt + reference pattern task.

Plan dùng **VN prose**, **EN identifier/code/SQL/commit message** (memory `feedback-language-split`).

---

## Task 0: SPIKE — Verify Zalo zca-js bridge 2026 readiness

**Depends on:** none
**Parallel-safe with:** Batch A tasks (foundation không đụng channel)
**Block:** toàn bộ Batch E (channel)
**Timebox:** 2 ngày
**Files:**
- Create: `spikes/zalo-2026/login.js` (port từ `archive/legacy:src/channels/zalo_bridge/login.js`)
- Create: `spikes/zalo-2026/bridge.js` (port từ legacy)
- Create: `spikes/zalo-2026/package.json` (port từ legacy)
- Create: `spikes/zalo-2026/probe_group_ops.js` (NEW — test `fetchGroupInfo` + `getAllGroups`)
- Create: `spikes/zalo-2026/.gitignore` (ignore `node_modules/`, `session.json`, `qr.png`)
- Create: `docs/spikes/2026-05-31-zalo-2026-readiness.md` (findings)
- Modify: `docs/superpowers/specs/2026-05-30-group-note-bot/10-tech-stack-infra.md` (sửa stack table: `zlapi-py` → `zca-js`, chỉ khi go decision)

**Acceptance:**
- [ ] QR login flow chạy: `qr.png` mở được, scan trên Zalo app → `session.json` xuất hiện
- [ ] Saved session reconnect: chạy `bridge.js` không cần scan lại
- [ ] Inbound DM text capture: gửi text từ acc khác → `data.uidFrom`, `threadId`, `data.content` đúng schema probe v1
- [ ] Inbound group text capture: vào nhóm test, gửi text → schema đúng
- [ ] Inbound image: gửi ảnh trong nhóm → `data.content` là object `{href, thumb, previewThumb, title}`
- [ ] Inbound mention bot: tag `@bot` trong nhóm → `data.mentions[]` có `uid === own_uid`
- [ ] Send group text: `node send.js group <gid> "test"` → tin xuất hiện trong app
- [ ] **NEW vs probe v1**: `api.getAllGroups()` trả về list groups bot đã ở
- [ ] **NEW vs probe v1**: `api.fetchGroupInfo(gid)` trả về member list
- [ ] Burst test: gửi 20 message liên tiếp trong 30s → không rate-limit ban
- [ ] Findings doc viết xong + go/no-go conclusion
- [ ] Spec stack table updated NẾU go

**Steps:**

- [ ] **Step 1: Workspace + port legacy code (đã xong trong session này)**

```bash
mkdir -p spikes/zalo-2026
cd spikes/zalo-2026
git show archive/legacy:src/channels/zalo_bridge/login.js > login.js
git show archive/legacy:src/channels/zalo_bridge/bridge.js > bridge.js
git show archive/legacy:src/channels/zalo_bridge/package.json > package.json
cat > .gitignore <<'EOF'
node_modules/
session.json
qr.png
log.jsonl
EOF
```

- [ ] **Step 2: Install deps**

```bash
cd spikes/zalo-2026
npm install
```

Expected: `zca-js@2.x` installed (package.json `^2.0.0-beta.27` cho phép minor upgrade), 0 vulnerabilities.

- [ ] **Step 3: QR login**

User cần 1 acc Zalo test sẵn sàng trên điện thoại.

```bash
node login.js
```

Expected:
- `qr.png` được mở qua `xdg-open`
- Scan QR → log "scanned by <name>"
- Log "session saved → session.json"
- Log "OK — user_id = <uid>"

Nếu fail: ghi error vào findings doc, xem zca-js v2.1+ API changes (loginQR signature có thể đã đổi).

- [ ] **Step 4: Saved session reconnect**

```bash
node bridge.js < /dev/null
```

Expected: bridge khởi động không scan QR lại; log "listener attached, own_id=<uid>".

- [ ] **Step 5: Inbound DM text**

Mở `bridge.js` running terminal. Từ máy/acc khác gửi text DM cho bot. Quan sát stdout JSONL.

Expected event shape (probe v1):
```json
{"type":"inbound","data":{"uidFrom":"<peer>","threadId":"<peer>","type":0,"cmd":501,"content":"hello"}}
```

Ghi vào findings: schema field còn đúng không? Cmd code còn 501?

- [ ] **Step 6: Inbound group text**

Bot phải ở trong 1 group test. Gửi text vào group.

Expected:
```json
{"type":"inbound","data":{"uidFrom":"<sender>","threadId":"<group_id>","type":1,"cmd":521,"content":"..."}}
```

- [ ] **Step 7: Inbound image trong group**

Gửi ảnh.

Expected `data.content` = object `{href, thumb, previewThumb, title}`. Schema còn match probe v1?

- [ ] **Step 8: Inbound mention bot**

Trong group, gửi `@bot test` (replace `@bot` bằng tên bot acc thật).

Expected `data.mentions[0].uid === own_uid`.

- [ ] **Step 9: Send message**

Tạo `send.js`:

```javascript
// spikes/zalo-2026/send.js
const fs = require('fs');
const path = require('path');
const { Zalo, ThreadType } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');
const [, , kind, threadId, ...rest] = process.argv;
const text = rest.join(' ');
if (!kind || !threadId || !text) {
  console.error('usage: node send.js {group|user} <thread_id> <text>');
  process.exit(1);
}
const tt = kind === 'group' ? ThreadType.Group : ThreadType.User;

(async () => {
  const session = JSON.parse(fs.readFileSync(SESSION_PATH));
  const zalo = new Zalo({ logging: false });
  const api = await zalo.login(session);
  const res = await api.sendMessage({ msg: text }, threadId, tt);
  console.log(JSON.stringify(res));
})().catch(e => { console.error('ERR:', e); process.exit(1); });
```

Run:
```bash
node send.js group <group_id> "test from bot"
```

Expected: log id message, tin xuất hiện trong app Zalo.

- [ ] **Step 10: NEW — Group ops probe**

Tạo `probe_group_ops.js`:

```javascript
// spikes/zalo-2026/probe_group_ops.js
const fs = require('fs');
const path = require('path');
const { Zalo } = require('zca-js');

const SESSION_PATH = path.join(__dirname, 'session.json');

(async () => {
  const session = JSON.parse(fs.readFileSync(SESSION_PATH));
  const zalo = new Zalo({ logging: false });
  const api = await zalo.login(session);

  console.log('=== getAllGroups ===');
  const groups = await api.getAllGroups();
  console.log(JSON.stringify(groups, null, 2).slice(0, 2000));

  const firstGid = Object.keys(groups.gridInfoMap || groups || {})[0];
  if (firstGid) {
    console.log(`=== fetchGroupInfo(${firstGid}) ===`);
    const info = await api.fetchGroupInfo(firstGid);
    console.log(JSON.stringify(info, null, 2).slice(0, 4000));
  }
})().catch(e => { console.error('ERR:', e); process.exit(1); });
```

Run:
```bash
node probe_group_ops.js
```

Expected:
- `getAllGroups()` trả về object có `gridInfoMap` hoặc array — ghi shape vào findings
- `fetchGroupInfo(gid)` trả về object có `memberIDs` hoặc `members` — ghi shape

Đây là phần probe v1 SKIP, MVP cần để `resolve_group_owner` ([§3.4](../specs/2026-05-30-group-note-bot/03-identity-channel-linking.md#34-phát-hiện-thành-viên-nhóm)) work.

- [ ] **Step 11: Burst rate-limit feel**

Test gửi 20 message trong 30s:

```bash
for i in $(seq 1 20); do
  node send.js group <group_id> "burst $i"
  sleep 1.5
done
```

Quan sát: có message nào fail không? Có ban không? Acc còn login được không sau test?

Ghi vào findings: cap ổn, hay cần throttle giảm xuống.

- [ ] **Step 12: Document findings**

Tạo `docs/spikes/2026-05-31-zalo-2026-readiness.md`:

```markdown
# Zalo 2026 Readiness — Spike 2026-05-31

**zca-js version installed:** <version từ `npm ls`>
**Probe v1 reference:** `docs/legacy/zalo-probe-findings.md` (Q4 2025)

## API matrix

| Capability | Status | Note |
|---|---|---|
| QR login + session save | <PASS/FAIL> | |
| Saved session reconnect | <PASS/FAIL> | |
| Inbound DM text shape | <PASS/FAIL> | <regression vs probe v1> |
| Inbound group text shape | <PASS/FAIL> | |
| Inbound image shape | <PASS/FAIL> | |
| Inbound mention detect | <PASS/FAIL> | |
| Send group text | <PASS/FAIL> | |
| getAllGroups | <PASS/FAIL> | <shape: ...> |
| fetchGroupInfo | <PASS/FAIL> | <shape: ...> |
| Burst 20msg/30s | <PASS/FAIL> | <ban? throttle?> |

## Conclusion

**Decision:** <GO | FORK | REPLACE>

<Lý do, blocker, next step>
```

- [ ] **Step 13: If GO — update spec stack**

```bash
# Sửa §10.1 stack table — replace zlapi-py row
# Hiện tại:
# | **Channel — Zalo** (MVP) | `zlapi-py` (port legacy) ... |
# Sửa thành:
# | **Channel — Zalo** (MVP) | `zca-js` Node bridge (port legacy zalo_bridge) ... |
```

Cũng update §10.2 `src/channels/zalo.py` → mô tả là Python wrapper subprocess Node bridge JSONL.

- [ ] **Step 14: Commit**

```bash
git add spikes/zalo-2026 docs/spikes/
git commit -m "spike(zalo): verify zca-js bridge 2026 readiness + group ops probe"
```

Nếu spec updated:
```bash
git add docs/superpowers/specs/2026-05-30-group-note-bot/10-tech-stack-infra.md
git commit -m "docs(spec): replace zlapi-py with zca-js in §10.1 stack (spike result)"
```

**Risk:**
- zca-js v2.1+ API có thể đã breaking change so với v2.0.0-beta.27 → login flow fail. Mitigation: đọc zca-js CHANGELOG, port legacy code adapt API mới.
- Zalo có thể đã thay đổi cookie/QR schema → relogin liên tục. Mitigation: ghi log full event trong findings, fork zca-js patch khi cần.
- Group ops `fetchGroupInfo` có thể yêu cầu admin role. Mitigation: ghi rõ trong findings; spec đã cover (§2.1.1 `requires_admin_role_for_core` = false, degrade gracefully).

**Fallback nếu spike FAIL hoàn toàn:**
1. Switch channel-MVP sang Telegram (đã có module-ready trong spec, python-telegram-bot v21+, webhook đầy đủ). User feedback memory `feedback-zalo-first` push back — coi như Plan B last resort.
2. Spike kéo dài thêm 3 ngày để fork/patch zca-js.

---

## Batch A — Foundation

Phải xong trước tất cả batch khác. 5 task, parallel-safe sau A1.

### Task A1: Project bootstrap

**Depends on:** none
**Parallel-safe with:** Task 0 (spike)
**Files:**
- Create: `pyproject.toml`
- Create: `docker/docker-compose.yml`
- Create: `docker/Dockerfile`
- Create: `.env.example`
- Create: `.gitignore` (additions for `.venv/`, `data/`, `*.pyc`, `.env`)
- Create: `src/__init__.py`
- Create: `src/main.py` (FastAPI app factory skeleton)
- Create: `src/config.py` (pydantic-settings)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/.gitkeep`
- Create: `scripts/restart.sh` (dev local restart — port từ memory `feedback-docker-rebuild`)

**Acceptance:**
- [ ] `docker compose -f docker/docker-compose.yml up -d postgres qdrant` chạy được
- [ ] `uv run uvicorn src.main:app --reload` start được; `/healthz` → `{"status":"ok"}`
- [ ] `alembic current` chạy không lỗi (chưa có revision)
- [ ] `pytest` chạy 0 test pass

**Steps:**

- [ ] **Step 1: pyproject.toml**

```toml
[project]
name = "smart-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "asyncpg>=0.30",
  "alembic>=1.13",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "httpx>=0.27",
  "structlog>=24.4",
  "qdrant-client>=1.12",
  "apscheduler>=3.10",
  "authlib>=1.3",
  "itsdangerous>=2.2",
  "cryptography>=43",
  "passlib[bcrypt]>=1.7",
  "jinja2>=3.1",
  "python-multipart>=0.0.12",
  "openai>=1.51",
  "google-generativeai>=0.8",
  "trafilatura>=1.12",
  "yt-dlp>=2024.10",
  "pypdf>=5.0",
  "python-docx>=1.1",
  "openpyxl>=3.1",
  "pillow>=11.0",
  "pillow-heif>=0.18",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=5.0",
  "mypy>=1.13",
  "ruff>=0.7",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
strict = true
python_version = "3.12"
```

- [ ] **Step 2: docker-compose**

```yaml
# docker/docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: smart
      POSTGRES_PASSWORD: smart
      POSTGRES_DB: smart_bot
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]
  qdrant:
    image: qdrant/qdrant:v1.12.4
    ports: ["6333:6333"]
    volumes: [qdrant_data:/qdrant/storage]
volumes:
  postgres_data:
  qdrant_data:
```

- [ ] **Step 3: .env.example**

```bash
POSTGRES_DSN=postgresql://smart:smart@localhost:5432/smart_bot
QDRANT_URL=http://localhost:6333

GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
SESSION_SECRET=<random 64 bytes>
FERNET_KEY=<base64 32 bytes>
OAUTH_REDIRECT_WHITELIST=http://localhost:8000/api/oauth/google/callback

SUPERADMIN_EMAILS=

PLATFORM_OPENAI_API_KEY=
PLATFORM_GROQ_API_KEY=

BANK_ACCOUNT_NUMBER=
BANK_ACCOUNT_NAME=
BANK_BIN=

DEFAULT_BOSS_COST_CAP_USD_DAILY=5
LOG_RAW_CONTENT=false
```

- [ ] **Step 4: src/config.py**

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_DSN: str
    QDRANT_URL: str = "http://localhost:6333"

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    SESSION_SECRET: str
    FERNET_KEY: str
    OAUTH_REDIRECT_WHITELIST: str = ""

    SUPERADMIN_EMAILS: str = ""

    PLATFORM_OPENAI_API_KEY: str = ""
    PLATFORM_GROQ_API_KEY: str = ""

    DEFAULT_BOSS_COST_CAP_USD_DAILY: float = 5.0
    LOG_RAW_CONTENT: bool = False

    @property
    def superadmin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.SUPERADMIN_EMAILS.split(",") if e.strip()}

    @property
    def redirect_whitelist(self) -> set[str]:
        return {u.strip() for u in self.OAUTH_REDIRECT_WHITELIST.split(",") if u.strip()}

settings = Settings()  # raises if required vars missing
```

- [ ] **Step 5: src/main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup hooks: DB pool, Qdrant client, EventBus, registries — fill in later tasks
    yield
    # shutdown hooks

app = FastAPI(title="SMART_bot", lifespan=lifespan)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
```

- [ ] **Step 6: Alembic init**

```bash
alembic init -t async migrations
```

Sửa `migrations/env.py` để load DSN từ `src.config.settings.POSTGRES_DSN`. Sửa `alembic.ini` để `sqlalchemy.url` rỗng (load via env.py).

- [ ] **Step 7: scripts/restart.sh**

```bash
#!/bin/bash
set -e
docker compose -f docker/docker-compose.yml up -d postgres qdrant
alembic upgrade head
exec uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
chmod +x scripts/restart.sh
```

- [ ] **Step 8: Smoke test**

```bash
docker compose -f docker/docker-compose.yml up -d postgres qdrant
uv venv && uv pip install -e ".[dev]"
cp .env.example .env  # fill SESSION_SECRET + FERNET_KEY
uv run uvicorn src.main:app --port 8000 &
sleep 2
curl -s localhost:8000/healthz
```

Expected: `{"status":"ok"}`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml docker/ .env.example .gitignore src/ tests/ alembic.ini migrations/ scripts/
git commit -m "feat(bootstrap): project skeleton — FastAPI + asyncpg + Qdrant + Alembic"
```

---

### Task A2: DB infrastructure

**Depends on:** A1
**Parallel-safe with:** A3, A4 (sau khi A2 base ready)
**Files:**
- Create: `src/infra/db.py` (asyncpg pool factory)
- Create: `src/infra/qdrant.py` (Qdrant client wrapper)
- Create: `src/infra/observability.py` (structlog setup)
- Create: `src/web/deps.py` (get_db dependency)
- Modify: `src/main.py` (wire lifespan: open pool, close pool)
- Create: `tests/integration/test_db_pool.py`

**Acceptance:**
- [ ] `app.state.db_pool` connects khi app startup
- [ ] `/healthz` mở rộng: `{"status":"ok","db":"ok","qdrant":"ok"}`
- [ ] Integration test connect được Postgres test container

**Steps:**

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_db_pool.py
import pytest
from src.infra.db import create_pool

@pytest.mark.asyncio
async def test_pool_query_one():
    pool = await create_pool()
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1")
    await pool.close()
    assert v == 1
```

- [ ] **Step 2: Run** — `pytest tests/integration/test_db_pool.py -v` → FAIL (no `create_pool`).

- [ ] **Step 3: Implement**

```python
# src/infra/db.py
import asyncpg
from src.config import settings

async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        settings.POSTGRES_DSN,
        min_size=2, max_size=20, command_timeout=30,
    )
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Wire lifespan in main.py**

```python
# src/main.py (replace lifespan)
from src.infra.db import create_pool
from src.infra.qdrant import create_qdrant
from src.infra.observability import configure_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.db_pool = await create_pool()
    app.state.qdrant = create_qdrant()
    yield
    await app.state.db_pool.close()
```

- [ ] **Step 6: Qdrant wrapper**

```python
# src/infra/qdrant.py
from qdrant_client import AsyncQdrantClient
from src.config import settings

def create_qdrant() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.QDRANT_URL)
```

- [ ] **Step 7: Observability**

```python
# src/infra/observability.py
import logging, structlog

REDACT_FIELDS = {"text", "media_text", "sender_name", "credentials_blob", "auth_blob", "api_key"}

def _redact(_, __, event_dict):
    for k in list(event_dict):
        if k in REDACT_FIELDS:
            v = event_dict[k]
            event_dict[k] = f"<redacted len={len(str(v))}>"
    return event_dict

def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

- [ ] **Step 8: Expand /healthz**

```python
# src/main.py
@app.get("/healthz")
async def healthz():
    db_ok = False; qdrant_ok = False
    try:
        async with app.state.db_pool.acquire() as c:
            await c.fetchval("SELECT 1"); db_ok = True
    except Exception: pass
    try:
        await app.state.qdrant.get_collections(); qdrant_ok = True
    except Exception: pass
    return {"status": "ok", "db": "ok" if db_ok else "fail", "qdrant": "ok" if qdrant_ok else "fail"}
```

- [ ] **Step 9: web/deps.py**

```python
# src/web/deps.py
from fastapi import Request
import asyncpg
async def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool
```

- [ ] **Step 10: Commit**

```bash
git add src/infra/ src/web/deps.py src/main.py tests/integration/
git commit -m "feat(infra): asyncpg pool + Qdrant client + structlog + /healthz"
```

---

### Task A3: Initial schema migration

**Depends on:** A1 (alembic init), A2 (DB pool)
**Parallel-safe with:** A4
**Files:**
- Create: `migrations/versions/0001_initial_schema.py` (Alembic revision — ALL tables in 1 migration vì greenfield)
- Create: `config/seeds/models.yaml` (referenced by [§7.2 spec](../specs/2026-05-30-group-note-bot/07-llm-abstraction.md#72-modelregistry--db--seed-file))
- Create: `config/seeds/llm_routes.yaml`
- Create: `config/seeds/feature_budgets.yaml`
- Create: `config/seeds/retrieval_pipelines.yaml`
- Create: `config/seeds/agent_triggers.yaml`
- Create: `config/seeds/note_templates.yaml`
- Create: `config/seeds/prompts/`
- Create: `migrations/data/0001_seed_config.py` (load seed YAML khi tables rỗng)

**Acceptance:**
- [ ] `alembic upgrade head` tạo đủ ~25 table không lỗi
- [ ] `alembic downgrade -1` revert clean
- [ ] Seed script idempotent: chạy 2 lần OK, không duplicate
- [ ] Bảng `models` có 4 row, `llm_routes` 12 row, `prompts` ≥4 row sau seed

**Steps:**

- [ ] **Step 1: Tables — derive từ spec sections**

Schema tổng hợp từ:
- §3.1, §3.3, §3.8: `users`, `account_links`, `linking_tokens`, `bot_accounts`, `bot_account_assignments`
- §4.6, §4.9: `group_notes`, `group_note_versions`, `note_templates`
- §5.2, §5.4, §5.6: `messages`, `media_cache`, `outbound_messages`
- §6.3, §6.4: `pins`, `memory_entries`
- §7.2, §7.3, §7.5, §7.6, §7.7: `models`, `llm_routes`, `prompts`, `token_usage`
- §15.7.3, §15.6, §15.8: `feature_budgets`, `retrieval_pipelines`, `agent_triggers`
- §13.3: `action_items`, `scheduled_reminders`
- §8.4: `boss_integrations`
- §14.2: `tool_call_log`
- §12: `admin_audit_log`

- [ ] **Step 2: Write migration upgrade()**

```python
# migrations/versions/0001_initial_schema.py
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("""
    CREATE TABLE users (
      id                       SERIAL PRIMARY KEY,
      email                    TEXT NOT NULL UNIQUE,
      name                     TEXT,
      google_sub               TEXT UNIQUE,
      password_hash            TEXT,
      role                     TEXT NOT NULL DEFAULT 'boss',
      subscription_status      TEXT NOT NULL DEFAULT 'trial',
      subscription_plan        TEXT,
      subscription_expiry      TIMESTAMPTZ,
      tz                       TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
      language                 TEXT NOT NULL DEFAULT 'vi',
      smart_model_id           BIGINT,
      fast_model_id            BIGINT,
      vision_model_id          BIGINT,
      api_keys_enc             BYTEA,
      cost_cap_usd_daily       NUMERIC(8,2) NOT NULL DEFAULT 5.0,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE bot_accounts (
      id                       BIGSERIAL PRIMARY KEY,
      provider                 TEXT NOT NULL,
      provider_user_id         TEXT NOT NULL,
      display_name             TEXT,
      account_kind             TEXT NOT NULL,
      ownership                TEXT NOT NULL,
      owner_boss_id            INTEGER REFERENCES users(id),
      credentials_blob_enc     BYTEA,
      status                   TEXT NOT NULL DEFAULT 'active',
      status_reason            TEXT,
      max_assigned_bosses      INTEGER NOT NULL DEFAULT 5,
      last_seen_at             TIMESTAMPTZ,
      msgs_received_total      BIGINT NOT NULL DEFAULT 0,
      msgs_sent_total          BIGINT NOT NULL DEFAULT 0,
      notes                    TEXT,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (provider, provider_user_id),
      CHECK (
        (ownership = 'platform'   AND owner_boss_id IS NULL) OR
        (ownership = 'boss_owned' AND owner_boss_id IS NOT NULL)
      )
    )
    """)

    op.execute("""
    CREATE TABLE bot_account_assignments (
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
      assignment_kind  TEXT NOT NULL,
      status           TEXT NOT NULL DEFAULT 'pending_accept',
      assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      assigned_by      INTEGER REFERENCES users(id),
      accepted_at      TIMESTAMPTZ,
      PRIMARY KEY (boss_id, provider)
    )
    """)
    op.execute("CREATE INDEX idx_assignments_account ON bot_account_assignments(bot_account_id)")

    op.execute("""
    CREATE TABLE account_links (
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      provider_user_id TEXT NOT NULL,
      linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (provider, provider_user_id)
    )
    """)
    op.execute("CREATE INDEX idx_account_links_boss ON account_links(boss_id)")

    op.execute("""
    CREATE TABLE linking_tokens (
      token            TEXT PRIMARY KEY,
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
      expires_at       TIMESTAMPTZ NOT NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at)")

    op.execute("""
    CREATE TABLE note_templates (
      id              BIGSERIAL PRIMARY KEY,
      name            TEXT NOT NULL,
      description     TEXT,
      is_system       BOOLEAN NOT NULL DEFAULT FALSE,
      owner_boss_id   INTEGER REFERENCES users(id),
      sections_json   JSONB NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_note_templates_owner ON note_templates(owner_boss_id)")

    op.execute("""
    CREATE TABLE group_notes (
      id                         BIGSERIAL PRIMARY KEY,
      boss_id                    INTEGER NOT NULL REFERENCES users(id),
      provider                   TEXT NOT NULL,
      chat_id                    TEXT NOT NULL,
      group_name                 TEXT,
      content                    TEXT NOT NULL DEFAULT '',
      manually_edited_sections   JSONB NOT NULL DEFAULT '[]'::jsonb,
      last_seen_message_id       BIGINT,
      status                     TEXT NOT NULL DEFAULT 'active',
      msg_count_7d               INTEGER NOT NULL DEFAULT 0,
      template_id                BIGINT REFERENCES note_templates(id),
      updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, provider, chat_id)
    )
    """)
    op.execute("CREATE INDEX idx_group_notes_boss ON group_notes(boss_id)")

    op.execute("""
    CREATE TABLE group_note_versions (
      id            BIGSERIAL PRIMARY KEY,
      group_note_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      content       TEXT NOT NULL,
      emitted_by    TEXT NOT NULL,
      emitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_group_note_versions_note ON group_note_versions(group_note_id, emitted_at DESC)")

    op.execute("""
    CREATE TABLE messages (
      id                 BIGSERIAL PRIMARY KEY,
      boss_id            INTEGER NOT NULL REFERENCES users(id),
      provider           TEXT NOT NULL,
      chat_id            TEXT NOT NULL,
      chat_type          TEXT NOT NULL,
      provider_msg_id    TEXT,
      reply_to_msg_id    BIGINT REFERENCES messages(id),
      sender_provider_id TEXT,
      sender_name        TEXT,
      text               TEXT,
      media_kind         TEXT,
      media_url          TEXT,
      media_text         TEXT,
      ts                 TIMESTAMPTZ NOT NULL,
      ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      fts                tsvector,
      UNIQUE (provider, chat_id, provider_msg_id)
    )
    """)
    op.execute("CREATE INDEX idx_messages_chat ON messages(boss_id, provider, chat_id, ts DESC)")
    op.execute("CREATE INDEX idx_messages_fts ON messages USING GIN(fts)")
    op.execute("""
    CREATE OR REPLACE FUNCTION messages_fts_trigger() RETURNS trigger AS $$
    BEGIN
      NEW.fts := to_tsvector('simple',
        unaccent(coalesce(NEW.text,'') || ' ' || coalesce(NEW.media_text,'')));
      RETURN NEW;
    END;$$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER trg_messages_fts BEFORE INSERT OR UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION messages_fts_trigger()")

    op.execute("""
    CREATE TABLE media_cache (
      id              BIGSERIAL PRIMARY KEY,
      source_key      TEXT NOT NULL,
      source_kind     TEXT NOT NULL,
      media_text      TEXT NOT NULL,
      title           TEXT,
      fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      expires_at      TIMESTAMPTZ,
      UNIQUE (source_key, source_kind)
    )
    """)
    op.execute("CREATE INDEX idx_media_cache_expires ON media_cache(expires_at)")

    op.execute("""
    CREATE TABLE outbound_messages (
      id                  BIGSERIAL PRIMARY KEY,
      boss_id             INTEGER NOT NULL REFERENCES users(id),
      provider            TEXT NOT NULL,
      chat_id             TEXT NOT NULL,
      reply_to_message_id BIGINT REFERENCES messages(id),
      content             TEXT NOT NULL,
      trigger             TEXT NOT NULL,
      sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      status              TEXT NOT NULL,
      error               TEXT
    )
    """)

    op.execute("""
    CREATE TABLE pins (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      message_id      BIGINT NOT NULL REFERENCES messages(id),
      note            TEXT,
      pinned_by       INTEGER NOT NULL REFERENCES users(id),
      pinned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (group_note_id, message_id)
    )
    """)
    op.execute("CREATE INDEX idx_pins_group ON pins(group_note_id)")

    op.execute("""
    CREATE TABLE memory_entries (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      scope           TEXT NOT NULL,
      key             TEXT,
      content         TEXT NOT NULL,
      meta_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
      qdrant_point_id TEXT,
      source          TEXT NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, scope, key)
    )
    """)
    op.execute("CREATE INDEX idx_memory_boss_scope ON memory_entries(boss_id, scope)")

    op.execute("""
    CREATE TABLE models (
      id                       BIGSERIAL PRIMARY KEY,
      name                     TEXT NOT NULL,
      provider                 TEXT NOT NULL,
      endpoint_kind            TEXT NOT NULL,
      base_url                 TEXT,
      tier                     TEXT NOT NULL,
      ctx_max                  INTEGER NOT NULL,
      capabilities             JSONB NOT NULL DEFAULT '[]'::jsonb,
      cost_per_1m_input_usd    NUMERIC(10,4),
      cost_per_1m_output_usd   NUMERIC(10,4),
      is_platform_default      BOOLEAN NOT NULL DEFAULT FALSE,
      is_active                BOOLEAN NOT NULL DEFAULT TRUE,
      notes                    TEXT,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (provider, name)
    )
    """)

    op.execute("""
    CREATE TABLE llm_routes (
      id                  BIGSERIAL PRIMARY KEY,
      feature             TEXT NOT NULL,
      condition_cel       TEXT,
      target_tier         TEXT NOT NULL,
      fallback_chain      JSONB NOT NULL DEFAULT '[]'::jsonb,
      weight              INTEGER NOT NULL DEFAULT 100,
      is_active           BOOLEAN NOT NULL DEFAULT TRUE,
      notes               TEXT,
      updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_llm_routes_feature ON llm_routes(feature) WHERE is_active")

    op.execute("""
    CREATE TABLE feature_budgets (
      feature                  TEXT PRIMARY KEY,
      max_input_tokens         INTEGER NOT NULL,
      max_output_tokens        INTEGER NOT NULL,
      trim_policy_json         JSONB NOT NULL,
      compression_strategy     TEXT NOT NULL DEFAULT 'none',
      cache_prefix_hint        TEXT,
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE retrieval_pipelines (
      feature        TEXT PRIMARY KEY,
      stages_json    JSONB NOT NULL,
      description    TEXT,
      updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE agent_triggers (
      id              BIGSERIAL PRIMARY KEY,
      op_name         TEXT NOT NULL,
      event_name      TEXT NOT NULL,
      debounce_json   JSONB,
      threshold_json  JSONB,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE prompts (
      id          BIGSERIAL PRIMARY KEY,
      key         TEXT NOT NULL,
      version     INTEGER NOT NULL,
      body        TEXT NOT NULL,
      is_active   BOOLEAN NOT NULL DEFAULT FALSE,
      notes       TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_by  INTEGER REFERENCES users(id),
      UNIQUE (key, version)
    )
    """)
    op.execute("CREATE UNIQUE INDEX idx_prompts_active_per_key ON prompts(key) WHERE is_active")

    op.execute("""
    CREATE TABLE token_usage (
      id                      BIGSERIAL PRIMARY KEY,
      boss_id                 INTEGER NOT NULL REFERENCES users(id),
      feature                 TEXT NOT NULL,
      operation               TEXT NOT NULL,
      provider                TEXT NOT NULL,
      model                   TEXT NOT NULL,
      tokens_in               INTEGER NOT NULL,
      tokens_out              INTEGER NOT NULL,
      tokens_cached           INTEGER NOT NULL DEFAULT 0,
      cost_usd                NUMERIC(10,6) NOT NULL,
      cost_saved_cache_usd    NUMERIC(10,6) NOT NULL DEFAULT 0,
      latency_ms              INTEGER NOT NULL,
      trace_id                TEXT,
      span_id                 TEXT,
      parent_span_id          TEXT,
      gen_ai_system           TEXT,
      gen_ai_request_model    TEXT,
      gen_ai_response_model   TEXT,
      gen_ai_operation_name   TEXT,
      called_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      status                  TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX idx_token_usage_boss_time ON token_usage(boss_id, called_at DESC)")
    op.execute("CREATE INDEX idx_token_usage_feature_time ON token_usage(feature, called_at DESC)")

    op.execute("""
    CREATE TABLE tool_call_log (
      id              BIGSERIAL PRIMARY KEY,
      trace_id        TEXT NOT NULL,
      span_id         TEXT NOT NULL,
      parent_span_id  TEXT,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      tool_name       TEXT NOT NULL,
      args_hash       TEXT NOT NULL,
      status          TEXT NOT NULL,
      latency_ms      INTEGER NOT NULL,
      error           TEXT,
      called_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_tool_call_log_trace ON tool_call_log(trace_id)")

    op.execute("""
    CREATE TABLE action_items (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      text            TEXT NOT NULL,
      assignee_name   TEXT,
      due_at          TIMESTAMPTZ,
      status          TEXT NOT NULL DEFAULT 'open',
      source          TEXT NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_action_items_boss_status ON action_items(boss_id, status)")
    op.execute("CREATE INDEX idx_action_items_due ON action_items(boss_id, due_at) WHERE status='open'")

    op.execute("""
    CREATE TABLE scheduled_reminders (
      id                BIGSERIAL PRIMARY KEY,
      boss_id           INTEGER NOT NULL REFERENCES users(id),
      text              TEXT NOT NULL,
      due_at            TIMESTAMPTZ NOT NULL,
      scope             TEXT NOT NULL,
      provider          TEXT,
      chat_id           TEXT,
      bot_account_id    BIGINT REFERENCES bot_accounts(id),
      recurring         TEXT,
      action_item_id    BIGINT REFERENCES action_items(id),
      status            TEXT NOT NULL DEFAULT 'pending',
      fired_at          TIMESTAMPTZ,
      last_error        TEXT,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_by_op     TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX idx_reminders_due ON scheduled_reminders(due_at, status) WHERE status='pending'")
    op.execute("CREATE INDEX idx_reminders_boss ON scheduled_reminders(boss_id, status)")

    op.execute("""
    CREATE TABLE boss_integrations (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      plugin_id       TEXT NOT NULL,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      auth_blob_enc   BYTEA,
      settings_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
      connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, plugin_id)
    )
    """)

    op.execute("""
    CREATE TABLE admin_audit_log (
      id              BIGSERIAL PRIMARY KEY,
      actor_user_id   INTEGER NOT NULL REFERENCES users(id),
      action          TEXT NOT NULL,
      target_kind     TEXT,
      target_id       TEXT,
      reason          TEXT,
      payload_json    JSONB,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # FK from users.smart/fast/vision_model_id deferred (forward ref)
    op.execute("ALTER TABLE users ADD CONSTRAINT fk_users_smart_model FOREIGN KEY (smart_model_id) REFERENCES models(id)")
    op.execute("ALTER TABLE users ADD CONSTRAINT fk_users_fast_model FOREIGN KEY (fast_model_id) REFERENCES models(id)")
    op.execute("ALTER TABLE users ADD CONSTRAINT fk_users_vision_model FOREIGN KEY (vision_model_id) REFERENCES models(id)")

def downgrade():
    for t in ["admin_audit_log","boss_integrations","scheduled_reminders","action_items",
              "tool_call_log","token_usage","prompts","agent_triggers","retrieval_pipelines",
              "feature_budgets","llm_routes","models","memory_entries","pins",
              "outbound_messages","media_cache","messages","group_note_versions",
              "group_notes","note_templates","linking_tokens","account_links",
              "bot_account_assignments","bot_accounts","users"]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS messages_fts_trigger()")
```

- [ ] **Step 3: Seed YAML files** — viết tay (xem spec §7.2 cho models, §15.6 cho retrieval, etc.). Vd `config/seeds/models.yaml`:

```yaml
- name: gpt-4o-mini
  provider: openai
  endpoint_kind: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision, prompt_cache]
  cost_per_1m_input_usd: 0.15
  cost_per_1m_output_usd: 0.60
  is_platform_default: true
  notes: MVP default smart + vision (fallback)

- name: llama-3.3-70b-versatile
  provider: groq
  endpoint_kind: openai_compat
  base_url: https://api.groq.com/openai/v1
  tier: fast
  ctx_max: 128000
  capabilities: [tool_use]
  cost_per_1m_input_usd: 0.59
  cost_per_1m_output_usd: 0.79
  is_platform_default: true
  notes: MVP default fast

- name: gpt-4o
  provider: openai
  endpoint_kind: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision, prompt_cache]
  cost_per_1m_input_usd: 2.50
  cost_per_1m_output_usd: 10.00
  is_platform_default: false

- name: gemini-2.0-flash
  provider: gemini
  endpoint_kind: gemini
  tier: fast
  ctx_max: 1000000
  capabilities: [tool_use, vision]
  cost_per_1m_input_usd: 0.10
  cost_per_1m_output_usd: 0.40
  is_platform_default: false
```

Tương tự cho `llm_routes.yaml`, `feature_budgets.yaml`, `retrieval_pipelines.yaml`, `agent_triggers.yaml`, `note_templates.yaml`, `prompts/<key>.yaml` — copy seed table từ §7.3, §15.7.3, §15.6, §15.8, §4.9 spec.

- [ ] **Step 4: Seed runner**

```python
# migrations/data/0001_seed_config.py
"""Seed config tables from config/seeds/ — idempotent."""
import asyncio, yaml, pathlib
import asyncpg
from src.config import settings

SEED_DIR = pathlib.Path(__file__).parents[2] / "config" / "seeds"

async def seed_models(conn):
    data = yaml.safe_load((SEED_DIR / "models.yaml").read_text())
    for m in data:
        await conn.execute("""
        INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                            capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
                            is_platform_default, is_active, notes)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,TRUE,$11)
        ON CONFLICT (provider, name) DO UPDATE SET
          base_url=EXCLUDED.base_url, tier=EXCLUDED.tier, ctx_max=EXCLUDED.ctx_max,
          capabilities=EXCLUDED.capabilities, cost_per_1m_input_usd=EXCLUDED.cost_per_1m_input_usd,
          cost_per_1m_output_usd=EXCLUDED.cost_per_1m_output_usd,
          is_platform_default=EXCLUDED.is_platform_default, notes=EXCLUDED.notes,
          updated_at=NOW()
        """, m["name"], m["provider"], m["endpoint_kind"], m.get("base_url"), m["tier"],
            m["ctx_max"], m.get("capabilities", []),
            m.get("cost_per_1m_input_usd"), m.get("cost_per_1m_output_usd"),
            m["is_platform_default"], m.get("notes"))

# tương tự cho llm_routes, feature_budgets, retrieval_pipelines, agent_triggers,
# note_templates, prompts — mỗi loader hàm riêng, ON CONFLICT UPDATE

async def main():
    conn = await asyncpg.connect(settings.POSTGRES_DSN)
    try:
        await seed_models(conn)
        # await seed_llm_routes(conn)  ... etc
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Run migration**

```bash
alembic upgrade head
python -m migrations.data.0001_seed_config
```

- [ ] **Step 6: Verify**

```bash
psql $POSTGRES_DSN -c "SELECT count(*) FROM models;"   # ≥4
psql $POSTGRES_DSN -c "SELECT count(*) FROM llm_routes;"   # ≥12
```

- [ ] **Step 7: Rollback test**

```bash
alembic downgrade base
alembic upgrade head
python -m migrations.data.0001_seed_config  # idempotent — không lỗi
```

- [ ] **Step 8: Commit**

```bash
git add migrations/ config/seeds/
git commit -m "feat(db): initial schema (~25 tables) + seed config"
```

---

### Task A4: Domain entities

**Depends on:** A1
**Parallel-safe with:** A2, A3, A5
**Files:**
- Create: `src/domain/__init__.py`
- Create: `src/domain/boss.py`, `bot_account.py`, `message.py`, `group_note.py`, `reminder.py`, `memory.py`, `model.py`, `pin.py`, `action_item.py`, `media_cache.py`, `prompt.py`

**Acceptance:**
- [ ] Mỗi entity = `@dataclass(frozen=True, slots=True)` (immutable, fast)
- [ ] Enum cho field categorical (`MemoryScope`, `BotAccountStatus`, `ReminderScope`, etc.)
- [ ] `mypy --strict src/domain/` pass
- [ ] Test 1 unit test creation + equality

**Steps:**

- [ ] **Step 1: Pattern**

```python
# src/domain/memory.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

class MemoryScope(StrEnum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"

@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    boss_id: int
    scope: MemoryScope
    key: str | None
    content: str
    meta: dict[str, Any] = field(default_factory=dict)
    qdrant_point_id: str | None = None
    source: str = "agent_tool"
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 2: Tương tự cho mọi entity** — schema mỗi entity reflect `migrations/0001` columns. Vd:

```python
# src/domain/bot_account.py
class BotAccountOwnership(StrEnum):
    PLATFORM = "platform"
    BOSS_OWNED = "boss_owned"

class BotAccountStatus(StrEnum):
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"
    BANNED = "banned"
    RATE_LIMITED = "rate_limited"
    PAUSED = "paused"

@dataclass(frozen=True, slots=True)
class BotAccount:
    id: int
    provider: str
    provider_user_id: str
    display_name: str | None
    account_kind: str
    ownership: BotAccountOwnership
    owner_boss_id: int | None
    status: BotAccountStatus
    max_assigned_bosses: int
    msgs_received_total: int
    msgs_sent_total: int
    last_seen_at: datetime | None
    # credentials_blob_enc KHÔNG vào domain — chỉ dispenser internal
```

- [ ] **Step 3: Test**

```python
# tests/unit/test_domain.py
from src.domain.memory import Memory, MemoryScope

def test_memory_immutable():
    m = Memory(id=1, boss_id=42, scope=MemoryScope.SEMANTIC,
               key="preferred_name", content="Đạt")
    assert m.scope == "semantic"
    with pytest.raises(Exception):  # frozen
        m.content = "x"
```

- [ ] **Step 4: Commit**

```bash
git add src/domain/ tests/unit/test_domain.py
git commit -m "feat(domain): immutable entities + enums"
```

---

### Task A5: Repository base + initial repos

**Depends on:** A2, A3, A4
**Parallel-safe with:** (no other tasks initially)
**Files:**
- Create: `src/repositories/__init__.py`
- Create: `src/repositories/base.py` (BossScopedRepo)
- Create: `src/repositories/users.py`, `bot_accounts.py`, `messages.py`, `group_notes.py`, `memory_entries.py`, `models.py`, `llm_routes.py`, `feature_budgets.py`, `prompts.py`, `note_templates.py`, `retrieval_pipelines.py`, `agent_triggers.py`, `reminders.py`, `action_items.py`, `outbound_messages.py`, `pins.py`, `media_cache.py`, `boss_integrations.py`, `token_usage.py`, `tool_call_log.py`, `bot_account_assignments.py`, `account_links.py`, `linking_tokens.py`, `admin_audit_log.py`
- Test: `tests/integration/test_repos/` (1 file/repo)

**Acceptance:**
- [ ] `BossScopedRepo` enforce `boss_id` qua constructor; method không nhận `boss_id` lẻ
- [ ] Mỗi repo có ≥3 method: `get`, `list`, `insert` (others: `update`, `delete` as needed)
- [ ] Mọi repo trả domain entity (KHÔNG dict)
- [ ] Integration test cho 5 repo trọng yếu (users, messages, group_notes, bot_accounts, memory_entries)

**Steps:**

- [ ] **Step 1: Base pattern**

```python
# src/repositories/base.py
from dataclasses import dataclass
import asyncpg

@dataclass(frozen=True)
class BossContext:
    boss_id: int
    user_role: str          # 'boss' | 'superadmin'

class BossScopedRepo:
    """Inject (db_pool, boss_context) via constructor.
    Subclasses must filter every query by self.ctx.boss_id."""
    def __init__(self, pool: asyncpg.Pool, ctx: BossContext):
        self.pool = pool
        self.ctx = ctx
```

- [ ] **Step 2: First repo (pattern-introducing) — users**

```python
# src/repositories/users.py
from src.domain.boss import Boss
from src.repositories.base import BossScopedRepo
import asyncpg

class UsersRepo(BossScopedRepo):
    async def get_me(self) -> Boss:
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM users WHERE id=$1", self.ctx.boss_id)
            return _row_to_boss(row)

    async def get_by_email(self, email: str) -> Boss | None:
        # superadmin operation — bypass boss_id filter
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM users WHERE email=$1", email.lower())
            return _row_to_boss(row) if row else None

    async def update_models(self, smart_id: int | None, fast_id: int | None,
                            vision_id: int | None) -> None:
        async with self.pool.acquire() as c:
            await c.execute("""
              UPDATE users SET smart_model_id=$2, fast_model_id=$3, vision_model_id=$4,
                               updated_at=NOW() WHERE id=$1
            """, self.ctx.boss_id, smart_id, fast_id, vision_id)

def _row_to_boss(r: asyncpg.Record) -> Boss:
    return Boss(
      id=r["id"], email=r["email"], name=r["name"], role=r["role"],
      tz=r["tz"], language=r["language"],
      smart_model_id=r["smart_model_id"], fast_model_id=r["fast_model_id"],
      vision_model_id=r["vision_model_id"],
      subscription_status=r["subscription_status"],
      subscription_expiry=r["subscription_expiry"],
      cost_cap_usd_daily=float(r["cost_cap_usd_daily"]),
    )
```

- [ ] **Step 3: Test**

```python
# tests/integration/test_repos/test_users.py
import pytest
from src.repositories.base import BossContext
from src.repositories.users import UsersRepo

@pytest.mark.asyncio
async def test_get_me(db_pool, boss_user):
    repo = UsersRepo(db_pool, BossContext(boss_id=boss_user.id, user_role="boss"))
    me = await repo.get_me()
    assert me.email == boss_user.email
```

`tests/conftest.py` cần fixture `db_pool` (truncate giữa test) + `boss_user` (INSERT 1 user).

- [ ] **Step 4: Repeat pattern cho mọi entity** — pattern-following, ngắn. Mỗi repo file ~50–100 dòng. Plan execution: 1 task subagent xử 1 batch ~5 repo.

Vd `messages.py`:

```python
class MessagesRepo(BossScopedRepo):
    async def insert(self, m: NewMessage) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval("""
              INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id,
                                    sender_provider_id, sender_name, text, media_kind,
                                    media_url, media_text, ts)
              VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
              ON CONFLICT (provider, chat_id, provider_msg_id) DO NOTHING
              RETURNING id
            """, self.ctx.boss_id, m.provider, m.chat_id, m.chat_type, m.provider_msg_id,
                m.sender_provider_id, m.sender_name, m.text, m.media_kind, m.media_url,
                m.media_text, m.ts)

    async def fts_search(self, query: str, chat_id: str | None, limit: int = 20) -> list[Message]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
              SELECT * FROM messages
              WHERE boss_id=$1
                AND ($2::TEXT IS NULL OR chat_id=$2)
                AND fts @@ plainto_tsquery('simple', unaccent($3))
              ORDER BY ts DESC LIMIT $4
            """, self.ctx.boss_id, chat_id, query, limit)
            return [_row_to_message(r) for r in rows]

    async def distinct_senders(self, chat_id: str, days: int = 30) -> list[str]:
        async with self.pool.acquire() as c:
            return [r["sender_provider_id"] for r in await c.fetch("""
              SELECT DISTINCT sender_provider_id FROM messages
              WHERE boss_id=$1 AND chat_id=$2 AND ts >= NOW() - ($3 || ' days')::INTERVAL
              AND sender_provider_id IS NOT NULL
            """, self.ctx.boss_id, chat_id, days)]
```

- [ ] **Step 5: Commit per ~5 repos**

```bash
git add src/repositories/base.py src/repositories/users.py src/repositories/messages.py \
        src/repositories/group_notes.py src/repositories/bot_accounts.py \
        src/repositories/memory_entries.py tests/integration/test_repos/
git commit -m "feat(repos): base BossScopedRepo + 5 core repos with integration tests"

# Tiếp commit cho batch repos còn lại
git add src/repositories/
git commit -m "feat(repos): config + reminder + plugin + audit repos"
```

---

## Batch B — Core abstractions

Sau Batch A. B1–B4 parallel-safe với nhau.

### Task B1: EventBus + event schema

**Depends on:** A1
**Parallel-safe with:** B2, B3, B4
**Files:**
- Create: `src/events/__init__.py`
- Create: `src/events/bus.py` (`EventBus` Protocol + `InMemoryEventBus`)
- Create: `src/events/schema.py` (Pydantic event models + version field)
- Create: `src/events/subscribers/__init__.py` (auto-import marker, sẽ populate trong batch D)
- Test: `tests/unit/test_event_bus.py`

**Acceptance:**
- [ ] `bus.publish(name, payload)` async → mọi subscriber chạy concurrent, mỗi subscriber timeout 10s default
- [ ] Subscriber raise exception → log error, KHÔNG block publisher
- [ ] Event payload validate qua Pydantic model trong `events/schema.py`
- [ ] Test publish + subscribe + concurrent fan-out + error isolation

**Steps:**

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_event_bus.py
import pytest, asyncio
from src.events.bus import InMemoryEventBus

@pytest.mark.asyncio
async def test_publish_subscribe():
    bus = InMemoryEventBus()
    received: list[dict] = []
    async def handler(payload):
        received.append(payload)
    bus.subscribe("test.event", handler)
    await bus.publish("test.event", {"x": 1})
    await asyncio.sleep(0.01)
    assert received == [{"x": 1}]

@pytest.mark.asyncio
async def test_concurrent_fanout():
    bus = InMemoryEventBus()
    counts = []
    async def h1(p): await asyncio.sleep(0.05); counts.append("h1")
    async def h2(p): counts.append("h2")
    bus.subscribe("e", h1); bus.subscribe("e", h2)
    await bus.publish("e", {})
    await asyncio.sleep(0.1)
    assert set(counts) == {"h1","h2"}

@pytest.mark.asyncio
async def test_error_isolation():
    bus = InMemoryEventBus()
    good_received = []
    async def bad(p): raise RuntimeError("boom")
    async def good(p): good_received.append(p)
    bus.subscribe("e", bad); bus.subscribe("e", good)
    await bus.publish("e", {"ok": True})
    await asyncio.sleep(0.01)
    assert good_received == [{"ok": True}]
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement bus**

```python
# src/events/bus.py
import asyncio, logging
from typing import Protocol, Callable, Awaitable
from collections import defaultdict
log = logging.getLogger(__name__)

EventName = str
EventPayload = dict
Handler = Callable[[EventPayload], Awaitable[None]]

class EventBus(Protocol):
    async def publish(self, event: EventName, payload: EventPayload) -> None: ...
    def subscribe(self, event: EventName, handler: Handler) -> None: ...

class InMemoryEventBus:
    def __init__(self, handler_timeout_s: float = 10.0):
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._timeout = handler_timeout_s

    def subscribe(self, event: EventName, handler: Handler) -> None:
        self._subs[event].append(handler)

    async def publish(self, event: EventName, payload: EventPayload) -> None:
        handlers = list(self._subs.get(event, []))
        if not handlers:
            return
        async def safe(h: Handler):
            try:
                await asyncio.wait_for(h(payload), timeout=self._timeout)
            except Exception as e:
                log.exception("event handler error", extra={"event": event, "handler": h.__qualname__})
        await asyncio.gather(*(safe(h) for h in handlers), return_exceptions=True)
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Event schema**

```python
# src/events/schema.py
from datetime import datetime
from typing import Literal
from pydantic import BaseModel

SCHEMA_VERSION = 1

class BaseEvent(BaseModel):
    schema_version: int = SCHEMA_VERSION
    occurred_at: datetime

class MessageCaptured(BaseEvent):
    message_id: int
    boss_id: int
    provider: str
    chat_id: str
    chat_type: Literal["dm", "group"]
    mentions_bot: bool
    sender_is_boss: bool

class NoteUpdated(BaseEvent):
    group_note_id: int
    boss_id: int
    version: int
    sections_changed: list[str]

class ReminderDue(BaseEvent):
    reminder_id: int
    boss_id: int

class RegistryInvalidated(BaseEvent):
    registry_name: Literal["models","prompts","llm_routes","feature_budgets",
                           "retrieval_pipelines","agent_triggers","note_templates"]
    key: str | None = None
    by_user_id: int

class OpFire(BaseEvent):
    """Published by TriggerEngine — operation handler subscribes to op.<name>.fire."""
    op_name: str
    reason: Literal["debounce","threshold","on_demand"]
    source_event: dict
```

Subscribers convert dict payload → model qua `Model.model_validate(payload)`.

- [ ] **Step 6: Wire into app lifespan**

```python
# src/main.py — extend lifespan
from src.events.bus import InMemoryEventBus

@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.db_pool = await create_pool()
    app.state.qdrant = create_qdrant()
    app.state.bus = InMemoryEventBus()
    yield
    await app.state.db_pool.close()
```

- [ ] **Step 7: Commit**

```bash
git add src/events/ tests/unit/test_event_bus.py src/main.py
git commit -m "feat(events): InMemoryEventBus + Pydantic event schema"
```

---

### Task B2: LLMGateway abstraction + MVP clients

**Depends on:** A2 (DB pool), A3 (models/llm_routes/feature_budgets/prompts tables), A5 (repos)
**Parallel-safe with:** B1, B3, B4
**Files:**
- Create: `src/llm/__init__.py`
- Create: `src/llm/base.py` (LLMGateway Protocol, LLMRequest/Response dataclass, ToolSpec)
- Create: `src/llm/clients/openai_compat.py`
- Create: `src/llm/clients/gemini.py`
- Create: `src/llm/native.py` (NativeGateway compose 2 client)
- Create: `src/llm/registry.py` (ModelRegistry cache, TTL 60s + invalidation event subscriber)
- Create: `src/llm/routes.py` (llm_routes resolver — feature → tier → model_id, condition + fallback)
- Create: `src/llm/budget.py` (feature_budgets resolver + trim policy executor)
- Create: `src/llm/cache_hint.py` (stable prefix structurer)
- Test: `tests/unit/test_llm_routes.py`, `test_llm_budget.py`, `test_llm_cache_hint.py`
- Test: `tests/integration/test_native_gateway_openai.py` (cần `PLATFORM_OPENAI_API_KEY` env; skip nếu missing)
- Test: `tests/integration/test_native_gateway_groq.py`

**Acceptance:**
- [ ] `LLMGateway.complete(LLMRequest)` → `LLMResponse` (content, tool_calls, usage)
- [ ] Model registry cache TTL 60s, invalidate qua `registry.invalidated` event
- [ ] llm_routes resolver: lookup feature → target_tier; sếp slot map tier → model_id; fallback ladder applied
- [ ] feature_budgets trim policy: drop oldest delta → drop low-score retrieval → truncate group_note
- [ ] cache_prefix_hint: structurer chia message thành 3 đoạn (stable / semi-stable / volatile)
- [ ] Token usage record vào `token_usage` table với OTel field
- [ ] Integration test: gọi thật OpenAI gpt-4o-mini + Groq llama; verify response

**Steps:**

- [ ] **Step 1: Define base types**

```python
# src/llm/base.py
from dataclasses import dataclass, field
from typing import Protocol, Literal, Any

@dataclass
class ChatMessage:
    role: Literal["system","user","assistant","tool"]
    content: str | list[dict]   # list for multimodal (image_url, text)
    name: str | None = None
    tool_call_id: str | None = None
    cache_breakpoint: bool = False   # marker for stable prefix end

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    # Plus per-§15.4 fields used by registry/dispatcher; LLM layer cares about top 3

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMRequest:
    feature: str
    messages: list[ChatMessage]
    boss_id: int
    tools: list[ToolSpec] | None = None
    required_caps: set[str] = field(default_factory=set)
    routing_hints: dict = field(default_factory=dict)
    cache_prefix_hint: str | None = None
    max_output_tokens: int | None = None
    temperature: float = 0.7

@dataclass
class LLMUsage:
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    latency_ms: int
    model: str
    provider: str

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: LLMUsage
    status: Literal["ok","error","rate_limited"]
    error: str | None = None

class LLMGateway(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
```

- [ ] **Step 2: OpenAI compatible client**

```python
# src/llm/clients/openai_compat.py
import time, asyncio
from openai import AsyncOpenAI, OpenAIError
from src.llm.base import LLMRequest, LLMResponse, LLMUsage, ToolCall, ChatMessage

class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat(self, model: str, req: LLMRequest) -> LLMResponse:
        msgs = [self._to_openai_msg(m) for m in req.messages]
        tools = [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.parameters}}
                 for t in (req.tools or [])] or None
        t0 = time.time()
        try:
            resp = await self.client.chat.completions.create(
                model=model, messages=msgs, tools=tools,
                temperature=req.temperature,
                max_tokens=req.max_output_tokens,
            )
        except OpenAIError as e:
            return LLMResponse(content=None, tool_calls=[], status="error",
                               error=str(e), usage=LLMUsage(0,0,0,int((time.time()-t0)*1000),model,"openai"))
        choice = resp.choices[0].message
        usage = resp.usage
        return LLMResponse(
            content=choice.content,
            tool_calls=[ToolCall(id=tc.id, name=tc.function.name, arguments=__import__("json").loads(tc.function.arguments))
                        for tc in (choice.tool_calls or [])],
            usage=LLMUsage(
                tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                tokens_cached=getattr(usage, "prompt_tokens_details", None) and
                              getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0,
                latency_ms=int((time.time()-t0)*1000), model=model, provider="openai_compat",
            ),
            status="ok",
        )

    @staticmethod
    def _to_openai_msg(m: ChatMessage) -> dict:
        d = {"role": m.role, "content": m.content}
        if m.role == "tool":
            d["tool_call_id"] = m.tool_call_id
        return d

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]
```

- [ ] **Step 3: Gemini client**

```python
# src/llm/clients/gemini.py
import time, json
import google.generativeai as genai
from src.llm.base import LLMRequest, LLMResponse, LLMUsage, ToolCall, ChatMessage

class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    async def chat(self, model: str, req: LLMRequest) -> LLMResponse:
        m = genai.GenerativeModel(model)
        contents = [{"role": "user" if msg.role!="assistant" else "model",
                     "parts": [msg.content if isinstance(msg.content, str) else msg.content[0].get("text","")]}
                    for msg in req.messages if msg.role != "system"]
        # Gemini doesn't natively support tool spec the same way; for MVP send tools as system instruction
        sys_msg = next((m.content for m in req.messages if m.role=="system"), None)
        t0 = time.time()
        try:
            resp = await m.generate_content_async(contents, system_instruction=sys_msg,
                                                  generation_config={"temperature": req.temperature,
                                                                     "max_output_tokens": req.max_output_tokens})
        except Exception as e:
            return LLMResponse(content=None, tool_calls=[], status="error", error=str(e),
                               usage=LLMUsage(0,0,0,int((time.time()-t0)*1000),model,"gemini"))
        return LLMResponse(
            content=resp.text, tool_calls=[],   # MVP: Gemini tool calls TODO Phase 1
            usage=LLMUsage(
              tokens_in=resp.usage_metadata.prompt_token_count,
              tokens_out=resp.usage_metadata.candidates_token_count,
              tokens_cached=getattr(resp.usage_metadata, "cached_content_token_count", 0),
              latency_ms=int((time.time()-t0)*1000), model=model, provider="gemini",
            ),
            status="ok",
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        # Gemini embedding API
        raise NotImplementedError("MVP uses OpenAI embed; Gemini embed Phase 1")
```

- [ ] **Step 4: Model registry cache + invalidation**

```python
# src/llm/registry.py
import time
from src.repositories.models import ModelsRepo
from src.domain.model import Model

class ModelRegistry:
    """Cache models DB (TTL 60s + invalidate on registry.invalidated event)."""
    def __init__(self, pool, bus):
        self._pool = pool; self._bus = bus
        self._cache: dict[int, Model] = {}
        self._loaded_at = 0.0
        bus.subscribe("registry.invalidated", self._handle_invalidate)

    async def _handle_invalidate(self, payload):
        if payload.get("registry_name") == "models":
            self._loaded_at = 0.0

    async def _ensure_loaded(self):
        if time.time() - self._loaded_at < 60:
            return
        repo = ModelsRepo(self._pool)
        all_models = await repo.list_active()
        self._cache = {m.id: m for m in all_models}
        self._loaded_at = time.time()

    async def get(self, model_id: int) -> Model:
        await self._ensure_loaded()
        return self._cache[model_id]

    async def platform_default(self, tier: str) -> Model:
        await self._ensure_loaded()
        for m in self._cache.values():
            if m.tier == tier and m.is_platform_default and m.is_active:
                return m
        raise LookupError(f"no platform default for tier={tier}")
```

- [ ] **Step 5: Routes resolver**

```python
# src/llm/routes.py
from src.domain.boss import Boss
from src.repositories.llm_routes import LLMRoutesRepo

async def pick_model(req, boss: Boss, pool, registry) -> tuple[Model, str]:
    """Return (model, route_id) — also resolves fallback when calling client fails (handled by NativeGateway loop)."""
    repo = LLMRoutesRepo(pool)
    route = await repo.match(req.feature, boss)  # condition_cel evaluator MVP = simple python eval on boss
    chosen_id = {"smart": boss.smart_model_id, "fast": boss.fast_model_id, "vision": boss.vision_model_id}[route.target_tier]
    if chosen_id is None:
        # Vision fallback: smart slot if has vision
        if route.target_tier == "vision" and boss.smart_model_id:
            sm = await registry.get(boss.smart_model_id)
            if "vision" in sm.capabilities:
                return sm, route.id
        chosen_id = (await registry.platform_default(route.target_tier)).id
    m = await registry.get(chosen_id)
    # Capability check (smart slot might miss vision)
    missing = req.required_caps - set(m.capabilities)
    if missing:
        for slot_id in [boss.vision_model_id, boss.smart_model_id, boss.fast_model_id]:
            if slot_id:
                alt = await registry.get(slot_id)
                if not (req.required_caps - set(alt.capabilities)):
                    return alt, route.id
        raise LookupError(f"no model with required caps={missing}")
    return m, route.id
```

CEL evaluator MVP đơn giản: parse `condition_cel` strings như `boss.subscription_plan == 'premium'` qua `ast.literal_eval` + restricted eval; reject expression có call. Hoặc skip MVP (condition_cel=NULL) — chỉ default route + manual override Phase 1.

- [ ] **Step 6: Budget + trim policy**

```python
# src/llm/budget.py
from src.repositories.feature_budgets import FeatureBudgetsRepo
import tiktoken

async def apply_budget(req, pool):
    repo = FeatureBudgetsRepo(pool)
    budget = await repo.get(req.feature)
    if not budget:
        return req
    req.max_output_tokens = req.max_output_tokens or budget.max_output_tokens
    enc = tiktoken.encoding_for_model("gpt-4o-mini")  # close approximation
    total = sum(len(enc.encode(m.content if isinstance(m.content,str) else str(m.content))) for m in req.messages)
    while total > budget.max_input_tokens:
        # Apply trim policy steps in order
        for step in budget.trim_policy:
            if step == "drop_oldest_delta":
                # Find oldest "user" message after first system — drop it
                for i, m in enumerate(req.messages):
                    if m.role == "user" and i > 1:
                        req.messages.pop(i); break
            elif step == "drop_low_score_retrieval":
                # Retrieval messages tagged with name="retrieval" — drop one
                for i, m in enumerate(req.messages):
                    if m.name == "retrieval":
                        req.messages.pop(i); break
            # ...other steps
        new_total = sum(len(enc.encode(m.content if isinstance(m.content,str) else str(m.content))) for m in req.messages)
        if new_total >= total:
            break  # no progress, give up
        total = new_total
    return req
```

- [ ] **Step 7: Prompt cache prefix structurer**

```python
# src/llm/cache_hint.py
def mark_cache_breakpoint(messages, hint: str | None):
    """Set cache_breakpoint=True on last message of stable prefix."""
    if not hint:
        return messages
    # MVP hints: "after_system", "after_semantic_memory", "after_group_note"
    boundary_role = {"after_system":"system", "after_semantic_memory":"user", "after_group_note":"user"}
    target = boundary_role.get(hint, "system")
    # Find last message matching target role within first 4 messages (stable prefix region)
    for i, m in enumerate(messages[:4]):
        if m.role == target:
            messages[i].cache_breakpoint = True
    return messages
```

OpenAI auto-cache nếu prefix ≥1024 token; breakpoint marker chỉ là hint cho gateway log / future Anthropic-style explicit cache.

- [ ] **Step 8: NativeGateway compose**

```python
# src/llm/native.py
import time
from src.llm.clients.openai_compat import OpenAICompatibleClient
from src.llm.clients.gemini import GeminiClient
from src.llm.routes import pick_model
from src.llm.budget import apply_budget
from src.llm.cache_hint import mark_cache_breakpoint
from src.repositories.users import UsersRepo
from src.repositories.token_usage import TokenUsageRepo
from src.repositories.base import BossContext

class NativeGateway:
    def __init__(self, pool, registry, llm_routes_repo, feature_budgets_repo,
                 api_key_provider):
        self.pool = pool; self.registry = registry
        self.routes = llm_routes_repo; self.budgets = feature_budgets_repo
        self.api_key_provider = api_key_provider   # callable(boss_id, provider) → key

    async def complete(self, req):
        boss = await UsersRepo(self.pool, BossContext(req.boss_id, "boss")).get_me()
        await apply_budget(req, self.pool)
        mark_cache_breakpoint(req.messages, req.cache_prefix_hint)

        model, route_id = await pick_model(req, boss, self.pool, self.registry)
        client = self._client_for(model, boss)

        resp = await client.chat(model.name, req)
        if resp.status != "ok":
            resp = await self._try_fallback(req, route_id, boss, model)

        await TokenUsageRepo(self.pool, BossContext(boss.id, boss.role)).insert(
            boss_id=boss.id, feature=req.feature, operation=req.routing_hints.get("op","unknown"),
            provider=model.provider, model=model.name,
            tokens_in=resp.usage.tokens_in, tokens_out=resp.usage.tokens_out,
            tokens_cached=resp.usage.tokens_cached, latency_ms=resp.usage.latency_ms,
            cost_usd=_compute_cost(model, resp.usage),
            cost_saved_cache_usd=_compute_cache_savings(model, resp.usage),
            status=resp.status, error=resp.error,
            trace_id=req.routing_hints.get("trace_id"),
            span_id=req.routing_hints.get("span_id"),
            gen_ai_system=model.provider, gen_ai_request_model=model.name,
            gen_ai_response_model=model.name, gen_ai_operation_name="chat",
        )
        return resp

    def _client_for(self, model, boss):
        key = self.api_key_provider(boss.id, model.provider)
        if model.endpoint_kind == "openai_compat":
            return OpenAICompatibleClient(model.base_url, key)
        if model.endpoint_kind == "gemini":
            return GeminiClient(key)
        raise ValueError(f"unknown endpoint_kind={model.endpoint_kind}")

    async def _try_fallback(self, req, route_id, boss, primary):
        route = await self.routes.get(route_id)
        for fb in route.fallback_chain:
            try:
                req2 = req
                tier = fb["tier"]
                # ... pick model for tier, try again
                # (simplified — full impl in execution)
            except Exception:
                continue
        return last_resp  # or error response
```

- [ ] **Step 9: API key provider helper**

```python
# src/llm/api_keys.py
from cryptography.fernet import Fernet
import json
from src.config import settings

_fernet = Fernet(settings.FERNET_KEY.encode())

def make_api_key_provider(pool):
    async def provider(boss_id: int, provider_name: str) -> str:
        async with pool.acquire() as c:
            blob = await c.fetchval("SELECT api_keys_enc FROM users WHERE id=$1", boss_id)
        if blob:
            keys = json.loads(_fernet.decrypt(bytes(blob)))
            if provider_name in keys:
                return keys[provider_name]
        # Fallback platform key
        env_key = {"openai": settings.PLATFORM_OPENAI_API_KEY,
                   "groq":   settings.PLATFORM_GROQ_API_KEY}.get(provider_name)
        if not env_key:
            raise LookupError(f"no api key for boss={boss_id} provider={provider_name}")
        return env_key
    return provider
```

- [ ] **Step 10: Wire into lifespan**

```python
# src/main.py
from src.llm.registry import ModelRegistry
from src.llm.native import NativeGateway
from src.llm.api_keys import make_api_key_provider
from src.repositories.llm_routes import LLMRoutesRepo
from src.repositories.feature_budgets import FeatureBudgetsRepo

# inside lifespan:
app.state.model_registry = ModelRegistry(app.state.db_pool, app.state.bus)
app.state.llm_gateway = NativeGateway(
    pool=app.state.db_pool,
    registry=app.state.model_registry,
    llm_routes_repo=LLMRoutesRepo(app.state.db_pool),
    feature_budgets_repo=FeatureBudgetsRepo(app.state.db_pool),
    api_key_provider=make_api_key_provider(app.state.db_pool),
)
```

- [ ] **Step 11: Integration test (live LLM)**

```python
# tests/integration/test_native_gateway_openai.py
import pytest, os
@pytest.mark.skipif(not os.getenv("PLATFORM_OPENAI_API_KEY"), reason="no key")
@pytest.mark.asyncio
async def test_complete_gpt4o_mini(native_gateway, boss_user):
    req = LLMRequest(feature="dm_general", boss_id=boss_user.id,
                     messages=[ChatMessage(role="user", content="Trả lời 'hi' không có dấu chấm.")])
    resp = await native_gateway.complete(req)
    assert resp.status == "ok"
    assert "hi" in resp.content.lower()
    assert resp.usage.tokens_in > 0
```

- [ ] **Step 12: Commit**

```bash
git add src/llm/ tests/unit/test_llm_*.py tests/integration/test_native_gateway_*.py src/main.py
git commit -m "feat(llm): LLMGateway + OpenAI compat + Gemini clients + routes + budget + cache hint"
```

---

### Task B3: MemoryProvider abstraction + InternalMemoryProvider

**Depends on:** A2, A3, A4, A5 (memory_entries repo), B2 (LLM embed for Qdrant upsert)
**Parallel-safe with:** B4
**Files:**
- Create: `src/memory/__init__.py`, `base.py`, `internal.py`
- Test: `tests/unit/test_memory_internal.py`, `tests/integration/test_memory_qdrant.py`

**Acceptance:**
- [ ] `MemoryProvider.recall(scope, query, boss_id, k)` trả top-k entries (semantic = qdrant vector; episodic = qdrant filter `kind=memory_episodic`)
- [ ] `write(scope, content, boss_id, meta, key?)` upsert (semantic) hoặc append (episodic); upsert Qdrant point khi content > 20 chars
- [ ] `forget(memory_id, boss_id)` DELETE row + Qdrant point
- [ ] Test recall semantic by key (no vector); recall semantic by query (vector); episodic recall (vector + filter)

**Steps:**

- [ ] **Step 1: Protocol**

```python
# src/memory/base.py
from typing import Protocol
from src.domain.memory import Memory, MemoryScope

class MemoryProvider(Protocol):
    async def recall(self, scope: MemoryScope, query: str | None,
                     boss_id: int, k: int = 5) -> list[Memory]: ...
    async def write(self, scope: MemoryScope, content: str, boss_id: int,
                    meta: dict | None = None, key: str | None = None) -> Memory: ...
    async def forget(self, memory_id: int, boss_id: int) -> None: ...
```

- [ ] **Step 2: Internal impl**

```python
# src/memory/internal.py
import uuid, json
from src.memory.base import MemoryProvider
from src.domain.memory import Memory, MemoryScope
from src.repositories.memory_entries import MemoryEntriesRepo

COLLECTION = "smart_bot"   # shared with messages

class InternalMemoryProvider:
    def __init__(self, pool, qdrant, llm_gateway):
        self.pool = pool; self.qdrant = qdrant; self.llm = llm_gateway

    async def write(self, scope, content, boss_id, meta=None, key=None) -> Memory:
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        if scope == MemoryScope.SEMANTIC and key:
            # Upsert by (boss_id, scope, key)
            existing = await repo.get_semantic_by_key(boss_id, key)
            if existing:
                await repo.update_content(existing.id, content)
                mem_id = existing.id; qpoint = existing.qdrant_point_id
            else:
                mem_id = await repo.insert(scope, key, content, meta or {}, source="agent_tool")
                qpoint = None
        else:
            mem_id = await repo.insert(scope, None, content, meta or {}, source="agent_tool")
            qpoint = None

        if len(content) > 20:
            qpoint = qpoint or str(uuid.uuid4())
            [vec] = await self.llm.embed([content], model="text-embedding-3-small")
            await self.qdrant.upsert(
                collection_name=COLLECTION,
                points=[{
                    "id": qpoint, "vector": vec,
                    "payload": {"boss_id": boss_id, "kind": f"memory_{scope.value}",
                                "memory_id": mem_id, "key": key},
                }],
            )
            await repo.set_qdrant_point(mem_id, qpoint)

        return await repo.get(mem_id)

    async def recall(self, scope, query, boss_id, k=5):
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        if query is None or len(query) < 3:
            return await repo.list_by_scope(scope, limit=k)
        [vec] = await self.llm.embed([query], model="text-embedding-3-small")
        hits = await self.qdrant.search(
            collection_name=COLLECTION, query_vector=vec,
            query_filter={"must": [
                {"key": "boss_id", "match": {"value": boss_id}},
                {"key": "kind",    "match": {"value": f"memory_{scope.value}"}},
            ]},
            limit=k,
        )
        mem_ids = [h.payload["memory_id"] for h in hits]
        return await repo.list_by_ids(mem_ids)

    async def forget(self, memory_id, boss_id):
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        m = await repo.get(memory_id)
        if m and m.qdrant_point_id:
            await self.qdrant.delete(collection_name=COLLECTION, points_selector=[m.qdrant_point_id])
        await repo.delete(memory_id)
```

- [ ] **Step 3: Qdrant collection ensure**

```python
# src/memory/internal.py — boot helper
async def ensure_collection(qdrant):
    cols = await qdrant.get_collections()
    if not any(c.name == COLLECTION for c in cols.collections):
        await qdrant.create_collection(COLLECTION,
            vectors_config={"size": 1536, "distance": "Cosine"})
```

Call từ lifespan after Qdrant init.

- [ ] **Step 4: Test**

```python
# tests/integration/test_memory_qdrant.py
@pytest.mark.asyncio
async def test_write_recall_semantic_by_key(memory_provider, boss_user):
    m = await memory_provider.write(MemoryScope.SEMANTIC,
        content="Nguyễn Văn Tân — sale lead", boss_id=boss_user.id, key="alias:anh Tân")
    assert m.key == "alias:anh Tân"
    found = await memory_provider.recall(MemoryScope.SEMANTIC, "Tân là ai", boss_user.id, k=3)
    assert any("Tân" in x.content for x in found)
```

- [ ] **Step 5: Commit**

```bash
git add src/memory/ tests/integration/test_memory_qdrant.py
git commit -m "feat(memory): MemoryProvider Protocol + InternalMemoryProvider (Qdrant-backed)"
```

---

### Task B4: Retrieval pipeline + stages

**Depends on:** A3, A5, B2 (embed)
**Parallel-safe with:** B1, B2, B3
**Files:**
- Create: `src/retrieval/__init__.py`, `base.py`, `pipeline.py`
- Create: `src/retrieval/stages/bm25.py`, `dense.py`, `fanout.py`, `rrf.py`, `mmr.py`
- Test: `tests/unit/test_rrf.py`, `test_mmr.py`
- Test: `tests/integration/test_retrieval_pipeline.py`

**Acceptance:**
- [ ] `RetrievalStage` Protocol; 5 stage implement (bm25, dense, fanout, rrf, mmr)
- [ ] `RetrievalPipeline.assemble(feature)` build từ `retrieval_pipelines.stages_json`
- [ ] Stage registry decorator-based (`@retrieval_stage(name=, kind=)`)
- [ ] Integration test: insert 30 message → run pipeline → top-5 đa dạng (MMR diversity > raw vector)

**Steps:**

- [ ] **Step 1: Base + registry**

```python
# src/retrieval/base.py
from dataclasses import dataclass
from typing import Protocol, Literal

@dataclass
class Hit:
    message_id: int
    score: float
    text: str
    sender: str | None
    ts: str
    source: str   # 'bm25' | 'dense' | 'rrf' | ...

@dataclass
class RetrievalContext:
    boss_id: int
    chat_id: str | None = None
    days: int | None = None

class RetrievalStage(Protocol):
    name: str
    kind: Literal["source","combinator","fuser","dedupe","reranker"]
    async def run(self, query: str, hits: list[Hit], ctx: RetrievalContext) -> list[Hit]: ...

_REGISTRY: dict[str, type] = {}

def retrieval_stage(name: str, kind: str):
    def deco(cls):
        cls.name = name; cls.kind = kind
        _REGISTRY[name] = cls
        return cls
    return deco

def get_stage_class(name: str):
    return _REGISTRY[name]
```

- [ ] **Step 2: BM25 source stage**

```python
# src/retrieval/stages/bm25.py
from src.retrieval.base import retrieval_stage, Hit, RetrievalContext

@retrieval_stage("bm25", "source")
class BM25Retriever:
    def __init__(self, pool, k: int = 30):
        self.pool = pool; self.k = k

    async def run(self, query, hits, ctx):
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
              SELECT id, text, sender_name, ts,
                     ts_rank(fts, plainto_tsquery('simple', unaccent($2))) AS rank
              FROM messages
              WHERE boss_id=$1
                AND ($3::TEXT IS NULL OR chat_id=$3)
                AND fts @@ plainto_tsquery('simple', unaccent($2))
              ORDER BY rank DESC LIMIT $4
            """, ctx.boss_id, query, ctx.chat_id, self.k)
        return [Hit(message_id=r["id"], score=float(r["rank"]), text=r["text"],
                    sender=r["sender_name"], ts=r["ts"].isoformat(), source="bm25") for r in rows]
```

- [ ] **Step 3: Dense source stage**

```python
# src/retrieval/stages/dense.py
@retrieval_stage("dense", "source")
class DenseRetriever:
    def __init__(self, pool, qdrant, llm_gateway, k: int = 30):
        self.pool = pool; self.qdrant = qdrant; self.llm = llm_gateway; self.k = k

    async def run(self, query, hits, ctx):
        [vec] = await self.llm.embed([query], model="text-embedding-3-small")
        filter_ = {"must": [
            {"key": "boss_id", "match": {"value": ctx.boss_id}},
            {"key": "kind", "match": {"value": "message"}},
        ]}
        if ctx.chat_id:
            filter_["must"].append({"key": "chat_id", "match": {"value": ctx.chat_id}})
        results = await self.qdrant.search(collection_name="smart_bot",
            query_vector=vec, query_filter=filter_, limit=self.k)
        # Need to load message details for each
        msg_ids = [r.payload["message_id"] for r in results]
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT id, text, sender_name, ts FROM messages WHERE id = ANY($1)", msg_ids)
        by_id = {r["id"]: r for r in rows}
        return [Hit(message_id=mid, score=float(r.score), text=by_id[mid]["text"],
                    sender=by_id[mid]["sender_name"], ts=by_id[mid]["ts"].isoformat(), source="dense")
                for mid, r in zip(msg_ids, results) if mid in by_id]
```

- [ ] **Step 4: ParallelFanout combinator**

```python
# src/retrieval/stages/fanout.py
import asyncio
@retrieval_stage("parallel_fanout", "combinator")
class ParallelFanout:
    def __init__(self, sources: list, k_each: int = 30):
        self.sources = sources; self.k_each = k_each

    async def run(self, query, hits, ctx):
        results = await asyncio.gather(*(s.run(query, [], ctx) for s in self.sources))
        merged = []
        for arr in results: merged.extend(arr)
        return merged
```

- [ ] **Step 5: RRF fuser**

```python
# src/retrieval/stages/rrf.py
from collections import defaultdict
@retrieval_stage("rrf", "fuser")
class RRFFuser:
    def __init__(self, k: int = 60):
        self.k = k

    async def run(self, query, hits, ctx):
        # Group by source, rank within source
        by_source = defaultdict(list)
        for h in hits: by_source[h.source].append(h)
        for s in by_source.values():
            s.sort(key=lambda x: -x.score)
        # Score per message: sum 1/(k+rank)
        scores: dict[int, float] = defaultdict(float)
        for src_hits in by_source.values():
            for rank, h in enumerate(src_hits, 1):
                scores[h.message_id] += 1.0 / (self.k + rank)
        # Pick first hit per message_id for content, score = rrf
        seen: dict[int, Hit] = {}
        for h in hits:
            if h.message_id not in seen:
                seen[h.message_id] = h
        out = [Hit(message_id=mid, score=scores[mid], text=seen[mid].text,
                   sender=seen[mid].sender, ts=seen[mid].ts, source="rrf")
               for mid in scores]
        out.sort(key=lambda x: -x.score)
        return out
```

- [ ] **Step 6: MMR dedupe**

```python
# src/retrieval/stages/mmr.py
@retrieval_stage("mmr", "dedupe")
class MMRDeduper:
    def __init__(self, lambda_: float = 0.5, k_out: int = 20):
        self.lambda_ = lambda_; self.k_out = k_out

    async def run(self, query, hits, ctx):
        # Simple proxy: cosine sim on token overlap (avoid extra embed cost)
        def sim(a, b):
            ta = set(a.text.lower().split())
            tb = set(b.text.lower().split())
            return len(ta & tb) / max(len(ta | tb), 1)
        selected: list[Hit] = []
        remaining = list(hits)
        while remaining and len(selected) < self.k_out:
            if not selected:
                best = remaining.pop(0)
            else:
                def mmr_score(h):
                    max_sim = max((sim(h, s) for s in selected), default=0)
                    return self.lambda_ * h.score - (1 - self.lambda_) * max_sim
                remaining.sort(key=lambda h: -mmr_score(h))
                best = remaining.pop(0)
            selected.append(best)
        return selected
```

- [ ] **Step 7: Pipeline assembler**

```python
# src/retrieval/pipeline.py
from src.retrieval.base import get_stage_class
from src.repositories.retrieval_pipelines import RetrievalPipelinesRepo

class RetrievalPipeline:
    def __init__(self, stages: list):
        self.stages = stages

    async def run(self, query, ctx):
        hits = []
        for s in self.stages:
            hits = await s.run(query, hits, ctx)
        return hits

async def assemble(feature: str, pool, qdrant, llm_gateway) -> RetrievalPipeline:
    repo = RetrievalPipelinesRepo(pool)
    cfg = await repo.get(feature)
    stages = []
    for stage_cfg in cfg.stages:
        cls = get_stage_class(stage_cfg["name"])
        args = stage_cfg.get("args", {})
        if stage_cfg["name"] == "parallel_fanout":
            sources = [_make_stage(s, args, pool, qdrant, llm_gateway) for s in args["sources"]]
            stages.append(cls(sources=sources, k_each=args.get("k_each", 30)))
        elif stage_cfg["name"] == "bm25":
            stages.append(cls(pool, **args))
        elif stage_cfg["name"] == "dense":
            stages.append(cls(pool, qdrant, llm_gateway, **args))
        else:
            stages.append(cls(**args))
    return RetrievalPipeline(stages)
```

- [ ] **Step 8: Force stage imports (so decorators register)**

```python
# src/retrieval/__init__.py
from src.retrieval.stages import bm25, dense, fanout, rrf, mmr  # noqa: F401
```

- [ ] **Step 9: Test + Commit**

```bash
git add src/retrieval/ tests/unit/test_rrf.py tests/unit/test_mmr.py tests/integration/test_retrieval_pipeline.py
git commit -m "feat(retrieval): pipeline + BM25/Dense/RRF/MMR stages"
```

---

## Batch C — Agent layer (registries + dispatcher)

Sau Batch B. C1 ↔ C2 parallel; C3 depends C2; C4 depends C3.

### Task C1: Tool registry + dispatcher

**Depends on:** A1, B2 (ToolSpec, LLMRequest đã định nghĩa)
**Parallel-safe with:** C2
**Files:**
- Create: `src/tools/__init__.py`, `base.py`, `registry.py`, `dispatcher.py`
- Create: `src/tools/core/__init__.py` (placeholder — core tools fill ở Batch D)
- Test: `tests/unit/test_tool_registry.py`, `test_tool_dispatcher.py`

**Acceptance:**
- [ ] `@tool` decorator register vào `_TOOL_REGISTRY`
- [ ] `registry.filter(op_name)` trả tools where `op_name in available_to`
- [ ] Dispatcher batch parallel-safe tools qua `asyncio.gather`; sequential cho non-parallel-safe
- [ ] Tool timeout enforce; log vào `tool_call_log`

**Steps:**

- [ ] **Step 1: Base types + decorator**

```python
# src/tools/base.py
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any

@dataclass
class ToolContext:
    boss_id: int
    boss_role: str
    pool: Any           # asyncpg.Pool
    qdrant: Any
    bus: Any
    memory: Any         # MemoryProvider
    retriever_factory: Any  # callable(feature) -> RetrievalPipeline
    llm: Any            # LLMGateway
    trace_id: str
    span_id: str

@dataclass
class ToolResult:
    content: Any
    error: str | None = None

@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict
    feature: str | None
    cost_class: str
    available_to: set[str]
    rate_limit: str | None
    timeout_s: int
    parallel_safe: bool
    handler: Callable[..., Awaitable[ToolResult]]
```

- [ ] **Step 2: Registry**

```python
# src/tools/registry.py
from src.tools.base import ToolDef
import inspect

_REGISTRY: dict[str, ToolDef] = {}

def tool(*, name: str, description: str, parameters: dict,
         feature: str | None = None, cost_class: str = "low",
         available_to: set[str] = frozenset(),
         rate_limit: str | None = None,
         timeout_s: int = 30, parallel_safe: bool = True):
    def deco(fn):
        _REGISTRY[name] = ToolDef(
            name=name, description=description, parameters=parameters,
            feature=feature, cost_class=cost_class,
            available_to=available_to, rate_limit=rate_limit,
            timeout_s=timeout_s, parallel_safe=parallel_safe, handler=fn,
        )
        return fn
    return deco

def get(name: str) -> ToolDef:
    return _REGISTRY[name]

def filter_for_op(op_name: str, allowed: set[str]) -> list[ToolDef]:
    return [t for n, t in _REGISTRY.items()
            if n in allowed and (not t.available_to or op_name in t.available_to)]
```

- [ ] **Step 3: Dispatcher**

```python
# src/tools/dispatcher.py
import asyncio, hashlib, json, time
from src.tools.base import ToolDef, ToolContext, ToolResult
from src.tools import registry
from src.repositories.tool_call_log import ToolCallLogRepo
from src.repositories.base import BossContext

class ToolDispatcher:
    def __init__(self, pool):
        self.pool = pool

    async def call_batch(self, calls: list, ctx: ToolContext) -> list[tuple[str, ToolResult]]:
        """Calls is list of ToolCall (from LLMResponse). Split into parallel/sequential."""
        results: list[tuple[str, ToolResult]] = []
        parallel: list = []
        sequential: list = []
        for c in calls:
            t = registry.get(c.name)
            (parallel if t.parallel_safe else sequential).append((c, t))
        # Parallel batch
        if parallel:
            par_results = await asyncio.gather(*(self._invoke(c, t, ctx) for c, t in parallel))
            results.extend(par_results)
        # Sequential
        for c, t in sequential:
            results.append(await self._invoke(c, t, ctx))
        return results

    async def _invoke(self, call, tool_def: ToolDef, ctx: ToolContext) -> tuple[str, ToolResult]:
        t0 = time.time()
        args_hash = hashlib.sha256(json.dumps(call.arguments, sort_keys=True).encode()).hexdigest()[:16]
        try:
            result = await asyncio.wait_for(
                tool_def.handler(ctx=ctx, **call.arguments),
                timeout=tool_def.timeout_s,
            )
            status = "ok"; error = None
        except asyncio.TimeoutError:
            result = ToolResult(content=None, error="timeout"); status = "timeout"; error = "timeout"
        except Exception as e:
            result = ToolResult(content=None, error=str(e)); status = "error"; error = str(e)
        latency_ms = int((time.time() - t0) * 1000)
        await ToolCallLogRepo(self.pool, BossContext(ctx.boss_id, ctx.boss_role)).insert(
            trace_id=ctx.trace_id, span_id=ctx.span_id, boss_id=ctx.boss_id,
            tool_name=tool_def.name, args_hash=args_hash, status=status,
            latency_ms=latency_ms, error=error,
        )
        return call.id, result
```

- [ ] **Step 4: Test**

```python
# tests/unit/test_tool_registry.py
from src.tools.registry import tool, filter_for_op

def test_register_and_filter():
    @tool(name="hello", description="say hi", parameters={"type":"object","properties":{}},
          available_to={"dm_responder"})
    async def _(ctx): return None
    fs = filter_for_op("dm_responder", allowed={"hello"})
    assert len(fs) == 1 and fs[0].name == "hello"
    assert filter_for_op("other_op", allowed={"hello"}) == []
```

- [ ] **Step 5: Commit**

```bash
git add src/tools/ tests/unit/test_tool_*.py
git commit -m "feat(tools): @tool decorator + registry + dispatcher (parallel-safe batch)"
```

---

### Task C2: Operation registry + decorator

**Depends on:** A1
**Parallel-safe with:** C1
**Files:**
- Create: `src/agents/__init__.py` (explicit import marker, populate ở Batch D)
- Create: `src/agents/base.py` (Operation Protocol, OpConfig)
- Create: `src/agents/registry.py`
- Test: `tests/unit/test_op_registry.py`

**Acceptance:**
- [ ] `@operation` decorator register class vào `_OP_REGISTRY`
- [ ] `OperationRegistry.all()` trả list class
- [ ] `OperationRegistry.by_name(name)` lookup
- [ ] Operation class có `_op_config: OpConfig` attribute

**Steps:**

- [ ] **Step 1: base.py**

```python
# src/agents/base.py
from dataclasses import dataclass, field
from typing import Callable, Type, Any, Protocol
from src.events.schema import BaseEvent

@dataclass
class OpConfig:
    name: str
    triggered_by: list[str]
    when: Callable[[BaseEvent], bool] | None
    deps_type: Type
    prompt_key: str
    feature: str
    memory_scopes: list[str]
    tools: set[str]
    timeout_s: int
    progress_mode: str   # 'none' | 'quick_ack'
    max_concurrency_per_bot_account: int
    cache_prefix_hint: str | None

class Operation(Protocol):
    _op_config: OpConfig
    async def handle(self, event: Any, ctx: Any) -> Any: ...
```

- [ ] **Step 2: registry.py**

```python
# src/agents/registry.py
from src.agents.base import OpConfig, Operation

_OP_REGISTRY: dict[str, type[Operation]] = {}

def operation(*, name, triggered_by, when=None, deps_type, prompt_key, feature,
              memory_scopes=(), tools=(), timeout_s=30, progress_mode="none",
              max_concurrency_per_bot_account=3, cache_prefix_hint=None):
    def deco(cls):
        cls._op_config = OpConfig(
            name=name, triggered_by=list(triggered_by), when=when,
            deps_type=deps_type, prompt_key=prompt_key, feature=feature,
            memory_scopes=list(memory_scopes), tools=set(tools),
            timeout_s=timeout_s, progress_mode=progress_mode,
            max_concurrency_per_bot_account=max_concurrency_per_bot_account,
            cache_prefix_hint=cache_prefix_hint,
        )
        _OP_REGISTRY[name] = cls
        return cls
    return deco

class OperationRegistry:
    @staticmethod
    def all() -> list[type[Operation]]:
        return list(_OP_REGISTRY.values())

    @staticmethod
    def by_name(name: str) -> type[Operation]:
        return _OP_REGISTRY[name]
```

- [ ] **Step 3: Test + Commit**

```bash
git add src/agents/__init__.py src/agents/base.py src/agents/registry.py tests/unit/test_op_registry.py
git commit -m "feat(agents): @operation decorator + OperationRegistry"
```

---

### Task C3: Event dispatcher + context builder

**Depends on:** B1 (EventBus), C2 (OperationRegistry)
**Parallel-safe with:** C1
**Files:**
- Create: `src/agents/dispatcher.py`, `context.py`
- Test: `tests/integration/test_op_dispatch.py`

**Acceptance:**
- [ ] `OperationDispatcher` subscribe ops vào EventBus theo `triggered_by`
- [ ] `when` predicate filter event trước handler chạy
- [ ] `build_context(deps_type, event)` resolve dataclass field từ app state + boss_id
- [ ] Tracing: `trace_op(op_name, boss_id)` context manager set trace_id/span_id vào contextvars
- [ ] Concurrency gate per bot_account (semaphore)

**Steps:**

- [ ] **Step 1: Tracing context**

```python
# src/agents/context.py
import contextvars, uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

@dataclass
class TraceCtx:
    trace_id: str
    span_id: str
    op_name: str
    boss_id: int

_current: contextvars.ContextVar[TraceCtx | None] = contextvars.ContextVar("trace", default=None)

@contextmanager
def trace_op(op_name: str, boss_id: int):
    tc = TraceCtx(trace_id=uuid.uuid4().hex, span_id=uuid.uuid4().hex,
                  op_name=op_name, boss_id=boss_id)
    tok = _current.set(tc)
    try: yield tc
    finally: _current.reset(tok)

def current() -> TraceCtx | None:
    return _current.get()
```

- [ ] **Step 2: build_context**

```python
# src/agents/context.py — continued
import dataclasses
from src.repositories.users import UsersRepo
from src.repositories.base import BossContext

async def build_context(deps_type, event, app_state):
    """Inspect deps_type dataclass fields; resolve from app_state + event."""
    boss_id = event["boss_id"]
    boss = await UsersRepo(app_state.db_pool, BossContext(boss_id, "boss")).get_me()
    available = {
        "boss": boss, "memory": app_state.memory_provider,
        "retriever_factory": app_state.retriever_factory,
        "llm": app_state.llm_gateway, "bus": app_state.bus, "db": app_state.db_pool,
        "qdrant": app_state.qdrant,
    }
    kwargs = {}
    for f in dataclasses.fields(deps_type):
        if f.name in available:
            kwargs[f.name] = available[f.name]
    return deps_type(**kwargs)
```

- [ ] **Step 3: Dispatcher**

```python
# src/agents/dispatcher.py
import asyncio
from collections import defaultdict
from src.agents.registry import OperationRegistry
from src.agents.context import trace_op, build_context

class OperationDispatcher:
    def __init__(self, bus, app_state):
        self.bus = bus; self.app_state = app_state
        self._sem_by_bot_acc: dict[int, asyncio.Semaphore] = {}

    def attach_all(self):
        for op_cls in OperationRegistry.all():
            cfg = op_cls._op_config
            for evname in cfg.triggered_by:
                self.bus.subscribe(evname, self._make_handler(op_cls))

    def _make_handler(self, op_cls):
        cfg = op_cls._op_config
        async def handler(event):
            if cfg.when and not cfg.when(event):
                return
            ctx = await build_context(cfg.deps_type, event, self.app_state)
            boss_id = event.get("boss_id")
            bot_acc_id = event.get("bot_account_id", 0)
            sem = self._sem_by_bot_acc.setdefault(
                bot_acc_id, asyncio.Semaphore(cfg.max_concurrency_per_bot_account))
            with trace_op(cfg.name, boss_id):
                async with sem:
                    await asyncio.wait_for(op_cls().handle(event, ctx), timeout=cfg.timeout_s)
        return handler
```

- [ ] **Step 4: Wire vào lifespan**

```python
# src/main.py
from src.agents.dispatcher import OperationDispatcher
import src.agents  # force import all op modules at startup

# in lifespan:
app.state.op_dispatcher = OperationDispatcher(app.state.bus, app.state)
app.state.op_dispatcher.attach_all()
```

- [ ] **Step 5: Commit**

```bash
git add src/agents/dispatcher.py src/agents/context.py tests/integration/test_op_dispatch.py src/main.py
git commit -m "feat(agents): EventBus → operation dispatcher + DI context + tracing"
```

---

### Task C4: Trigger engine (debounce + threshold)

**Depends on:** C3
**Parallel-safe with:** (none — final agent-layer piece)
**Files:**
- Create: `src/agents/triggers.py` (Debounce, Threshold, TriggerSpec, TriggerEngine, `@trigger` decorator)
- Test: `tests/unit/test_trigger_engine.py`

**Acceptance:**
- [ ] `@trigger(op=, event=, debounce=, threshold=, on_demand_tools=)` decorator
- [ ] Debounce: timer reset mỗi event cùng key; fire after window
- [ ] Threshold: counter increment; fire khi đạt; reset
- [ ] `TriggerEngine.attach(spec)` subscribe vào EventBus, publish `op.<op>.fire` khi đạt điều kiện
- [ ] Test: 30 message trong threshold=30 → fire 1 lần; reset counter

**Steps:**

- [ ] **Step 1: Spec types**

```python
# src/agents/triggers.py
import asyncio
from dataclasses import dataclass
from typing import Callable, Any

def parse_window(s: str) -> float:
    if s.endswith("s"): return float(s[:-1])
    if s.endswith("m"): return float(s[:-1]) * 60
    if s.endswith("h"): return float(s[:-1]) * 3600
    return float(s)

@dataclass
class Debounce:
    key: str           # e.g. "boss_id,chat_id"
    window: str        # e.g. "10m"
    @property
    def window_sec(self): return parse_window(self.window)

@dataclass
class Threshold:
    key: str
    count: int

@dataclass
class TriggerSpec:
    op_name: str
    event: str
    debounce: Debounce | None = None
    threshold: Threshold | None = None
    key_fn: Callable[[dict], str] = lambda e: ""

_TRIGGER_REGISTRY: list[TriggerSpec] = []

def trigger(*, op: str, event: str, debounce: Debounce | None = None,
            threshold: Threshold | None = None, on_demand_tools=()):
    def deco(cls_or_fn):
        # Build key_fn from debounce/threshold key spec
        keys = (debounce.key if debounce else threshold.key).split(",")
        def kfn(e: dict) -> str:
            return ":".join(f"{k}={e.get(k.strip(),'')}" for k in keys)
        _TRIGGER_REGISTRY.append(TriggerSpec(
            op_name=op, event=event, debounce=debounce, threshold=threshold, key_fn=kfn))
        return cls_or_fn
    return deco
```

- [ ] **Step 2: Engine**

```python
# src/agents/triggers.py — continued
class TriggerEngine:
    def __init__(self, bus):
        self.bus = bus
        self._debounce_timers: dict[str, asyncio.TimerHandle] = {}
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def attach_all(self):
        for spec in _TRIGGER_REGISTRY:
            self._attach_one(spec)

    def _attach_one(self, spec: TriggerSpec):
        async def handler(event: dict):
            key = f"{spec.op_name}:{spec.event}:{spec.key_fn(event)}"
            async with self._lock:
                if spec.threshold:
                    self._counters[key] = self._counters.get(key, 0) + 1
                    if self._counters[key] >= spec.threshold.count:
                        await self._fire(spec, event, "threshold")
                        self._counters[key] = 0
                        self._cancel_debounce(key)
                        return
                if spec.debounce:
                    self._cancel_debounce(key)
                    loop = asyncio.get_event_loop()
                    self._debounce_timers[key] = loop.call_later(
                        spec.debounce.window_sec,
                        lambda: asyncio.create_task(self._fire(spec, event, "debounce", key)),
                    )
        self.bus.subscribe(spec.event, handler)

    def _cancel_debounce(self, key):
        t = self._debounce_timers.pop(key, None)
        if t: t.cancel()

    async def _fire(self, spec, event, reason, key=None):
        if key: self._debounce_timers.pop(key, None)
        await self.bus.publish(f"op.{spec.op_name}.fire",
            {"reason": reason, "source_event": event, "boss_id": event.get("boss_id")})
```

- [ ] **Step 3: Wire vào lifespan**

```python
# src/main.py
from src.agents.triggers import TriggerEngine

# in lifespan:
app.state.trigger_engine = TriggerEngine(app.state.bus)
app.state.trigger_engine.attach_all()
```

- [ ] **Step 4: Commit**

```bash
git add src/agents/triggers.py tests/unit/test_trigger_engine.py src/main.py
git commit -m "feat(agents): trigger engine (debounce + threshold) → publish op.<name>.fire"
```

---

## Batch D — Operations + core tools

Sau Batch C. D1 pattern-introducing; D2/D3/D4 reference D1. D1–D4 parallel-safe sau khi core tools (D0) xong.

### Task D0: Core tools — implement 16 tools từ §6.3

**Depends on:** C1 (tool registry), B2 (LLM), B3 (memory), B4 (retrieval), A5 (repos)
**Files:**
- Create: `src/tools/core/search.py` (search_history, find_exact_quote)
- Create: `src/tools/core/notes.py` (read_group_note, refresh_group_note, edit_group_note, pin_message, unpin_message)
- Create: `src/tools/core/action_items.py` (list_action_items, mark_action_item)
- Create: `src/tools/core/reminders.py` (set_reminder, list_reminders, cancel_reminder)
- Create: `src/tools/core/memory.py` (remember, forget)
- Create: `src/tools/core/meta.py` (list_groups, current_time)
- Create: `src/tools/core/web.py` (fetch_url)
- Modify: `src/tools/__init__.py` (force import core/*)
- Test: `tests/integration/test_core_tools.py` (1 test/tool)

**Acceptance:**
- [ ] 16 tool registered (verify via `len(registry._REGISTRY) == 16`)
- [ ] Each tool integration test pass

**Steps:**

- [ ] **Step 1: Pattern — `remember` tool**

```python
# src/tools/core/memory.py
from src.tools.registry import tool
from src.tools.base import ToolResult
from src.domain.memory import MemoryScope

@tool(
    name="remember",
    description="Lưu thông tin về sếp/người xung quanh để nhớ cho lần sau. Vd: remember('preferred_name','Đạt'), remember('alias:anh Tân', 'Nguyễn Văn Tân — sale lead')",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Khóa ngữ nghĩa, vd 'preferred_name' hoặc 'alias:Tân'"},
            "value": {"type": "string", "description": "Giá trị cần nhớ"},
        },
        "required": ["key", "value"],
    },
    available_to={"dm_responder","in_group_responder"},
    parallel_safe=False,
)
async def remember(ctx, key: str, value: str) -> ToolResult:
    m = await ctx.memory.write(MemoryScope.SEMANTIC, content=value, boss_id=ctx.boss_id, key=key)
    return ToolResult(content={"memory_id": m.id, "key": key})

@tool(
    name="forget",
    description="Xoá entry memory đã nhớ trước đó",
    parameters={"type": "object", "properties": {"memory_id":{"type":"integer"}}, "required":["memory_id"]},
    available_to={"dm_responder"},
    parallel_safe=False,
)
async def forget(ctx, memory_id: int) -> ToolResult:
    await ctx.memory.forget(memory_id, ctx.boss_id)
    return ToolResult(content={"ok": True})
```

- [ ] **Step 2: search_history**

```python
# src/tools/core/search.py
@tool(
    name="search_history",
    description="Tìm trong lịch sử chat, hybrid (FTS + vector + RRF + MMR). Trả top-20 đoạn liên quan nhất.",
    parameters={
        "type":"object",
        "properties":{
            "query":{"type":"string"},
            "group_id":{"type":"string","nullable":True,"description":"Lọc theo 1 nhóm; null = tất cả nhóm"},
            "days":{"type":"integer","nullable":True,"description":"Giới hạn số ngày gần đây"},
        },
        "required":["query"],
    },
    feature="qa_with_search", cost_class="medium",
    available_to={"dm_responder","in_group_responder"},
    rate_limit="search:{boss_id}:30/min", parallel_safe=True, timeout_s=15,
)
async def search_history(ctx, query: str, group_id: str | None = None, days: int | None = None) -> ToolResult:
    from src.retrieval.base import RetrievalContext
    pipeline = await ctx.retriever_factory("qa_with_search")
    hits = await pipeline.run(query, RetrievalContext(boss_id=ctx.boss_id, chat_id=group_id, days=days))
    return ToolResult(content=[{
        "message_id": h.message_id, "score": h.score, "text": h.text,
        "sender": h.sender, "ts": h.ts,
    } for h in hits[:20]])

@tool(
    name="find_exact_quote",
    description="Tìm chính xác câu trích từ lịch sử (FTS exact). Trả author + ts + context ±3 message.",
    parameters={"type":"object","properties":{"fragment":{"type":"string"},"group_id":{"type":"string","nullable":True}},"required":["fragment"]},
    available_to={"dm_responder","in_group_responder"}, parallel_safe=True,
)
async def find_exact_quote(ctx, fragment: str, group_id: str | None = None) -> ToolResult:
    from src.repositories.messages import MessagesRepo
    from src.repositories.base import BossContext
    repo = MessagesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    matches = await repo.fts_exact(fragment, group_id, limit=5)
    out = []
    for m in matches:
        before, after = await repo.context_around(m.id, n=3)
        out.append({"author": m.sender_name, "ts": m.ts.isoformat(), "full_text": m.text,
                    "context_before": [b.text for b in before], "context_after": [a.text for a in after]})
    return ToolResult(content=out)
```

- [ ] **Step 3: notes tools**

```python
# src/tools/core/notes.py
@tool(name="read_group_note",
      description="Đọc note hiện tại của 1 nhóm",
      parameters={"type":"object","properties":{"group_id":{"type":"string"}},"required":["group_id"]},
      available_to={"dm_responder","in_group_responder"}, parallel_safe=True)
async def read_group_note(ctx, group_id: str):
    from src.repositories.group_notes import GroupNotesRepo
    from src.repositories.base import BossContext
    repo = GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    note = await repo.get_by_chat(group_id)
    return ToolResult(content={"content": note.content if note else "", "group_name": note.group_name if note else None})

@tool(name="refresh_group_note",
      description="Yêu cầu cập nhật ngay note của 1 nhóm (không đợi debounce)",
      parameters={"type":"object","properties":{"group_id":{"type":"string"}},"required":["group_id"]},
      available_to={"dm_responder","in_group_responder"},
      feature="note_update", cost_class="high", parallel_safe=False, timeout_s=60)
async def refresh_group_note(ctx, group_id: str):
    await ctx.bus.publish("op.note_updater.fire", {
        "reason": "on_demand", "boss_id": ctx.boss_id, "chat_id": group_id,
    })
    return ToolResult(content={"queued": True})

@tool(name="edit_group_note",
      description="Sửa 1 section của note (LLM viết section mới hoặc xoá)",
      parameters={"type":"object","properties":{
          "group_id":{"type":"string"},"section_key":{"type":"string"},"new_content":{"type":"string"}},
          "required":["group_id","section_key","new_content"]},
      available_to={"dm_responder"}, parallel_safe=False)
async def edit_group_note(ctx, group_id: str, section_key: str, new_content: str):
    from src.services.note_service import NoteService
    svc = NoteService(ctx.pool, ctx.bus, ctx.llm)
    await svc.edit_section(ctx.boss_id, group_id, section_key, new_content, by="llm")
    return ToolResult(content={"ok": True})

@tool(name="pin_message",
      description="Ghim 1 tin nhắn vào section 'Đã pin' của note",
      parameters={"type":"object","properties":{"message_id":{"type":"integer"},"note":{"type":"string","nullable":True}},"required":["message_id"]},
      available_to={"dm_responder","in_group_responder"}, parallel_safe=False)
async def pin_message(ctx, message_id: int, note: str | None = None):
    from src.services.note_service import NoteService
    svc = NoteService(ctx.pool, ctx.bus, ctx.llm)
    pin_id = await svc.pin(ctx.boss_id, message_id, note=note)
    return ToolResult(content={"pin_id": pin_id})

@tool(name="unpin_message",
      parameters={"type":"object","properties":{"pin_id":{"type":"integer"}},"required":["pin_id"]},
      description="Bỏ ghim", available_to={"dm_responder"}, parallel_safe=False)
async def unpin_message(ctx, pin_id: int):
    from src.repositories.pins import PinsRepo
    from src.repositories.base import BossContext
    await PinsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).delete(pin_id)
    return ToolResult(content={"ok": True})
```

- [ ] **Step 4: action_items**

```python
# src/tools/core/action_items.py
@tool(name="list_action_items",
      description="Liệt kê việc đang mở (open) / đã xong (done) cross-group hoặc theo nhóm",
      parameters={"type":"object","properties":{
          "group_id":{"type":"string","nullable":True},
          "status":{"type":"string","enum":["open","done","cancelled"],"default":"open"}}},
      available_to={"dm_responder","in_group_responder"}, parallel_safe=True)
async def list_action_items(ctx, group_id: str | None = None, status: str = "open"):
    from src.repositories.action_items import ActionItemsRepo
    from src.repositories.base import BossContext
    items = await ActionItemsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).list(group_id=group_id, status=status)
    return ToolResult(content=[{"id":i.id, "text":i.text, "assignee":i.assignee_name,
                                "due_at": i.due_at.isoformat() if i.due_at else None,
                                "status":i.status} for i in items])

@tool(name="mark_action_item",
      description="Đánh dấu việc done/cancel",
      parameters={"type":"object","properties":{
          "item_id":{"type":"integer"},
          "status":{"type":"string","enum":["done","cancelled"]}},
          "required":["item_id","status"]},
      available_to={"dm_responder","in_group_responder"}, parallel_safe=False)
async def mark_action_item(ctx, item_id: int, status: str):
    from src.repositories.action_items import ActionItemsRepo
    from src.repositories.base import BossContext
    await ActionItemsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).update_status(item_id, status)
    return ToolResult(content={"ok": True})
```

- [ ] **Step 5: reminders**

```python
# src/tools/core/reminders.py
from datetime import datetime
@tool(name="set_reminder",
      description="Đặt 1 nhắc. Phân tích `due_at` từ text natural language ('mai 3h', '15:00 T5') trước khi gọi (engine sẽ parse).",
      parameters={"type":"object","properties":{
          "text":{"type":"string","description":"Nội dung nhắc, vd 'nộp báo cáo Q2'"},
          "due_at_iso":{"type":"string","description":"Thời điểm ISO 8601 (TZ sếp)"},
          "scope":{"type":"string","enum":["group","dm"]},
          "target_chat_id":{"type":"string","nullable":True,"description":"Group ID nếu scope=group; null thì lấy current context"},
          "recurring":{"type":"string","nullable":True,"description":"daily | weekly:mon,wed,fri | null"},
      },"required":["text","due_at_iso","scope"]},
      feature="reminder_parse", cost_class="low",
      available_to={"dm_responder","in_group_responder"}, parallel_safe=False)
async def set_reminder(ctx, text: str, due_at_iso: str, scope: str,
                      target_chat_id: str | None = None, recurring: str | None = None):
    from src.services.reminder_service import ReminderService
    svc = ReminderService(ctx.pool, ctx.bus)
    rid = await svc.create(boss_id=ctx.boss_id, text=text, due_at=datetime.fromisoformat(due_at_iso),
                           scope=scope, chat_id=target_chat_id, recurring=recurring,
                           created_by_op=ctx.op_name if hasattr(ctx,"op_name") else "unknown")
    return ToolResult(content={"reminder_id": rid})

@tool(name="list_reminders",
      parameters={"type":"object","properties":{
          "status":{"type":"string","enum":["pending","fired","cancelled","failed"],"default":"pending"},
          "group_id":{"type":"string","nullable":True}}},
      description="Liệt kê reminder của sếp",
      available_to={"dm_responder","in_group_responder"}, parallel_safe=True)
async def list_reminders(ctx, status: str = "pending", group_id: str | None = None):
    from src.repositories.reminders import RemindersRepo
    from src.repositories.base import BossContext
    items = await RemindersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).list(status=status, chat_id=group_id)
    return ToolResult(content=[{"id":r.id, "text":r.text, "due_at":r.due_at.isoformat(),
                                "scope":r.scope, "chat_id":r.chat_id, "recurring":r.recurring} for r in items])

@tool(name="cancel_reminder",
      parameters={"type":"object","properties":{"reminder_id":{"type":"integer"}},"required":["reminder_id"]},
      description="Huỷ 1 reminder pending",
      available_to={"dm_responder"}, parallel_safe=False)
async def cancel_reminder(ctx, reminder_id: int):
    from src.repositories.reminders import RemindersRepo
    from src.repositories.base import BossContext
    await RemindersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).cancel(reminder_id)
    return ToolResult(content={"ok": True})
```

- [ ] **Step 6: meta + web**

```python
# src/tools/core/meta.py
from datetime import datetime
from zoneinfo import ZoneInfo
@tool(name="list_groups",
      parameters={"type":"object","properties":{}},
      description="Liệt kê các nhóm sếp đã link",
      available_to={"dm_responder"}, parallel_safe=True)
async def list_groups(ctx):
    from src.repositories.group_notes import GroupNotesRepo
    from src.repositories.base import BossContext
    notes = await GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).list_all()
    return ToolResult(content=[{"chat_id":n.chat_id, "group_name":n.group_name,
                                "provider":n.provider, "updated_at":n.updated_at.isoformat()} for n in notes])

@tool(name="current_time",
      parameters={"type":"object","properties":{}},
      description="Thời gian hiện tại theo TZ của sếp",
      available_to={"dm_responder","in_group_responder"}, parallel_safe=True)
async def current_time(ctx):
    from src.repositories.users import UsersRepo
    from src.repositories.base import BossContext
    boss = await UsersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role)).get_me()
    now = datetime.now(ZoneInfo(boss.tz))
    return ToolResult(content={"iso": now.isoformat(), "tz": boss.tz})

# src/tools/core/web.py
@tool(name="fetch_url",
      parameters={"type":"object","properties":{"url":{"type":"string"}},"required":["url"]},
      description="Fetch + extract URL/YouTube/file → text + title",
      feature="url_summarize", cost_class="medium",
      available_to={"dm_responder","in_group_responder"}, parallel_safe=True, timeout_s=30)
async def fetch_url(ctx, url: str):
    from src.media.registry import find_adapter
    adapter = find_adapter(url=url)  # decides URL/YouTube/etc
    result = await adapter.extract(url=url)
    return ToolResult(content={"title": result.title, "text": result.media_text[:20000]})
```

- [ ] **Step 7: Force imports**

```python
# src/tools/__init__.py
from src.tools.core import search, notes, action_items, reminders, memory, meta, web  # noqa
```

- [ ] **Step 8: Test stub for each**

```python
# tests/integration/test_core_tools.py
import pytest
from src.tools.registry import get

@pytest.mark.asyncio
async def test_remember(tool_ctx, boss_user):
    fn = get("remember").handler
    r = await fn(ctx=tool_ctx, key="preferred_name", value="Đạt")
    assert r.content["key"] == "preferred_name"
```

(viết tương tự cho 15 tool còn lại — fixture `tool_ctx` build trong conftest)

- [ ] **Step 9: Commit**

```bash
git add src/tools/core/ src/tools/__init__.py tests/integration/test_core_tools.py
git commit -m "feat(tools): 16 core tools (search/notes/action/reminder/memory/meta/web)"
```

---

### Task D1: DMResponder (pattern-introducing operation)

**Depends on:** B2, B3, B4, C1, C2, C3, D0
**Files:**
- Create: `src/agents/dm_responder.py`
- Create: `src/agents/agent_loop.py` (shared agent loop helper)
- Create: `config/seeds/prompts/dm_general.yaml`
- Modify: `src/agents/__init__.py` (import dm_responder)
- Test: `tests/integration/test_dm_responder.py` (end-to-end stubbed channel)

**Acceptance:**
- [ ] DMResponder subscribe `message.captured` với `when=chat_type==dm AND sender_is_boss`
- [ ] Agent loop: build context → llm.complete → loop tool calls → final answer
- [ ] Memory recall semantic + episodic injected vào system prompt
- [ ] Test: stub channel send 1 DM → bot reply có tool_calls + content

**Steps:**

- [ ] **Step 1: Shared agent_loop**

```python
# src/agents/agent_loop.py
from src.llm.base import LLMRequest, ChatMessage
from src.tools.registry import filter_for_op
from src.tools.dispatcher import ToolDispatcher

async def run_agent(op_cls, event, ctx):
    cfg = op_cls._op_config
    # Build initial messages
    system_prompt = await _load_prompt(cfg.prompt_key, ctx)
    semantic = await ctx.memory.recall(MemoryScope.SEMANTIC, None, ctx.boss.id, k=20)
    episodic = await ctx.memory.recall(MemoryScope.EPISODIC, event.get("text",""), ctx.boss.id, k=5)
    msgs = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="Memory: " + _format_memory(semantic, episodic),
                    name="memory_block"),
        ChatMessage(role="user", content=event["text"]),
    ]
    tools = [_to_toolspec(t) for t in filter_for_op(cfg.name, allowed=cfg.tools)]
    dispatcher = ToolDispatcher(ctx.db)
    for _ in range(5):
        req = LLMRequest(feature=cfg.feature, messages=msgs, boss_id=ctx.boss.id, tools=tools,
                         cache_prefix_hint=cfg.cache_prefix_hint or "after_semantic_memory",
                         routing_hints={"op": cfg.name})
        resp = await ctx.llm.complete(req)
        if not resp.tool_calls:
            return resp.content
        tool_ctx = _build_tool_ctx(ctx, op_name=cfg.name)
        results = await dispatcher.call_batch(resp.tool_calls, tool_ctx)
        msgs.append(ChatMessage(role="assistant", content=resp.content or "",
                                # ... tool_calls payload
                                ))
        for call_id, r in results:
            msgs.append(ChatMessage(role="tool", tool_call_id=call_id,
                                    content=str(r.content) if r.error is None else f"ERROR: {r.error}"))
    return "(em xin lỗi, em hơi loạn — vui lòng thử lại)"
```

- [ ] **Step 2: DMResponder**

```python
# src/agents/dm_responder.py
from dataclasses import dataclass
from src.agents.registry import operation
from src.agents.agent_loop import run_agent
from src.events.schema import MessageCaptured
from src.services.outbound_service import OutboundService

@dataclass
class DMContext:
    boss: any
    memory: any
    retriever_factory: any
    llm: any
    bus: any
    db: any
    qdrant: any

@operation(
    name="dm_responder",
    triggered_by=["message.captured"],
    when=lambda e: e.get("chat_type") == "dm" and e.get("sender_is_boss") is True,
    deps_type=DMContext,
    prompt_key="dm_general", feature="dm_general",
    memory_scopes=["semantic","episodic"],
    tools={"search_history","list_groups","list_reminders","set_reminder","cancel_reminder",
           "pin_message","find_exact_quote","remember","forget","fetch_url",
           "list_action_items","mark_action_item","edit_group_note","read_group_note",
           "refresh_group_note","current_time"},
    timeout_s=30, progress_mode="quick_ack",
    cache_prefix_hint="after_semantic_memory",
)
class DMResponder:
    async def handle(self, event, ctx: DMContext):
        text = event.get("text","")
        # Quick ack pattern
        outbound = OutboundService(ctx.db, ctx.bus)
        # Predict: nếu intent classify cho thấy "Q&A search" → ack first
        # MVP: always ack short for DM (Phase 1 conditional based on length)
        # ... skipped for brevity; full impl invokes LLM-fast intent_classify if message > 60 chars

        answer = await run_agent(DMResponder, event, ctx)
        await outbound.send(boss_id=ctx.boss.id, provider=event["provider"],
                            chat_id=event["chat_id"], content=answer, trigger="dm")
```

- [ ] **Step 3: Prompt seed**

```yaml
# config/seeds/prompts/dm_general.yaml
key: dm_general
version: 1
is_active: true
body: |
  Em là thư ký riêng của sếp {{ boss.name or 'anh' }}. Trả lời:
  - Lịch sự, ngắn gọn, đúng trọng tâm. Mặc định xưng "em", gọi sếp là "anh".
  - Nói tiếng Việt (trừ khi sếp đổi sang EN).
  - KHÔNG dùng emoji, KHÔNG bullet quá dài. Văn phong thư ký, không AI-themed.
  - Khi cần thông tin từ lịch sử nhóm, dùng tool `search_history` hoặc `find_exact_quote`.
  - Khi sếp giao việc/đặt nhắc, gọi `set_reminder` (parse thời gian theo TZ sếp).
  - Khi sếp nói "cứ gọi tôi là X" hoặc define alias, gọi `remember`.

  Memory về sếp + người xung quanh có sẵn ở phần memory bên dưới — đọc trước
  khi trả lời để dùng đúng tên/alias.
notes: MVP DM responder prompt
```

- [ ] **Step 4: OutboundService stub** (Batch E fill thật)

```python
# src/services/outbound_service.py
class OutboundService:
    def __init__(self, pool, bus):
        self.pool = pool; self.bus = bus
    async def send(self, boss_id, provider, chat_id, content, trigger):
        # MVP stub: log + INSERT outbound_messages; Batch E adapter consume + actually send
        await self.bus.publish("outbound.send", {
            "boss_id": boss_id, "provider": provider, "chat_id": chat_id,
            "content": content, "trigger": trigger,
        })
```

- [ ] **Step 5: Test (mocked LLM + memory)**

```python
# tests/integration/test_dm_responder.py
@pytest.mark.asyncio
async def test_dm_responder_handles_simple_question(app_state, boss_user, monkeypatch):
    # Mock LLM to return direct answer (no tool calls)
    async def fake_complete(req):
        return LLMResponse(content="Chào anh", tool_calls=[], status="ok",
                          usage=LLMUsage(10,5,0,100,"gpt-4o-mini","openai_compat"))
    monkeypatch.setattr(app_state.llm_gateway, "complete", fake_complete)
    # Subscribe collector
    sent = []
    app_state.bus.subscribe("outbound.send", lambda p: sent.append(p) or asyncio.sleep(0))
    # Publish event
    await app_state.bus.publish("message.captured", {
        "message_id": 1, "boss_id": boss_user.id, "provider": "zalo",
        "chat_id": "boss-dm", "chat_type": "dm", "sender_is_boss": True,
        "text": "Hi", "mentions_bot": False,
    })
    await asyncio.sleep(0.5)
    assert any(s["content"] == "Chào anh" for s in sent)
```

- [ ] **Step 6: Commit**

```bash
git add src/agents/dm_responder.py src/agents/agent_loop.py src/services/outbound_service.py \
        config/seeds/prompts/dm_general.yaml tests/integration/test_dm_responder.py
git commit -m "feat(agents): DMResponder + shared agent_loop + dm_general prompt"
```

---

### Task D2: GroupNoteUpdater + trigger declarations

**Depends on:** D0, D1 (agent_loop shared)
**Files:**
- Create: `src/agents/note_updater.py`
- Create: `src/services/note_service.py` (update note logic — lock, version, template render)
- Create: `config/seeds/prompts/note_update.yaml`
- Test: `tests/integration/test_note_updater.py`

**Acceptance:**
- [ ] NoteUpdater subscribe `op.note_updater.fire` (from TriggerEngine)
- [ ] `@trigger` declare debounce=10m + threshold=30 keyed by `boss_id,chat_id`, event=`message.captured`, when=group msg
- [ ] LLM rebuild note theo template `sections_json`; preserve `manually_edited_sections` + `append_only` (Đã quyết)
- [ ] Version INSERT vào `group_note_versions`; publish `note.updated`

**Steps:**

- [ ] **Step 1: NoteService**

```python
# src/services/note_service.py
import asyncio
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.note_templates import NoteTemplatesRepo
from src.repositories.messages import MessagesRepo
from src.repositories.base import BossContext
from src.llm.base import LLMRequest, ChatMessage

class NoteService:
    def __init__(self, pool, bus, llm):
        self.pool = pool; self.bus = bus; self.llm = llm
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def update(self, boss_id, provider, chat_id):
        lock = self._locks.setdefault((boss_id, provider, chat_id), asyncio.Lock())
        async with lock:
            ctx = BossContext(boss_id, "boss")
            notes = GroupNotesRepo(self.pool, ctx)
            tmpl = NoteTemplatesRepo(self.pool)
            messages = MessagesRepo(self.pool, ctx)

            note = await notes.get_or_create(provider, chat_id)
            template = await tmpl.get(note.template_id or await tmpl.system_default_id())
            delta = await messages.fetch_after_id(chat_id, note.last_seen_message_id or 0, limit=200)
            if not delta:
                return
            prompt = await self._build_prompt(template, note.content, delta,
                                              note.manually_edited_sections)
            req = LLMRequest(feature="note_update", boss_id=boss_id,
                            messages=[ChatMessage(role="system", content=prompt)],
                            cache_prefix_hint="after_system",
                            routing_hints={"op":"note_updater"})
            resp = await self.llm.complete(req)
            new_content = resp.content or note.content
            await notes.update_content(note.id, new_content, last_msg_id=delta[-1].id,
                                       version_emitter="llm")
            await self.bus.publish("note.updated", {
                "group_note_id": note.id, "boss_id": boss_id,
                "version": note.version + 1, "sections_changed": []
            })
```

- [ ] **Step 2: NoteUpdater op + trigger**

```python
# src/agents/note_updater.py
from dataclasses import dataclass
from src.agents.registry import operation
from src.agents.triggers import trigger, Debounce, Threshold

@dataclass
class NoteUpdaterCtx:
    boss: any
    db: any
    bus: any
    llm: any
    memory: any

@trigger(
    op="note_updater",
    event="message.captured",
    debounce=Debounce(key="boss_id,chat_id", window="10m"),
    threshold=Threshold(key="boss_id,chat_id", count=30),
)
@operation(
    name="note_updater",
    triggered_by=["op.note_updater.fire"],
    when=None,
    deps_type=NoteUpdaterCtx,
    prompt_key="note_update", feature="note_update",
    memory_scopes=[], tools=set(),
    timeout_s=120, progress_mode="none", max_concurrency_per_bot_account=1,
    cache_prefix_hint="after_system",
)
class NoteUpdater:
    async def handle(self, event, ctx: NoteUpdaterCtx):
        from src.services.note_service import NoteService
        src_ev = event.get("source_event", event)
        await NoteService(ctx.db, ctx.bus, ctx.llm).update(
            boss_id=ctx.boss.id,
            provider=src_ev["provider"], chat_id=src_ev["chat_id"],
        )
```

Note: `@trigger` filter chỉ event group messages — TriggerEngine cần know about `chat_type==group` predicate. Update trigger decorator to accept `when=` for trigger-side filter:

```python
# src/agents/triggers.py — add when= to TriggerSpec; trigger() accepts when=
# Handler checks before incrementing
```

- [ ] **Step 3: Prompt seed**

```yaml
# config/seeds/prompts/note_update.yaml
key: note_update
version: 1
is_active: true
body: |
  Cập nhật note nhóm theo template bên dưới. Mỗi section có {key, title, behavior, llm_hint, writable_by}.
  - behavior=rolling: ghi đè full
  - behavior=append_only: chỉ thêm bullet mới, KHÔNG xoá cũ
  - behavior=task_list: format `- [ ] {assignee} — {task} · {due}`
  - behavior=manual_pin: BỎ QUA (do user pin tay)
  - behavior=computed: BỎ QUA (do code tính)
  Section trong manually_edited_sections: GIỮ NGUYÊN.

  Template: {{ template_json }}
  Note hiện tại:
  {{ current_note }}

  Delta messages (mới nhất ở cuối):
  {{ delta }}

  Output: markdown mới đúng thứ tự section, heading theo title. KHÔNG emoji.
```

- [ ] **Step 4: Test + Commit**

```bash
git add src/agents/note_updater.py src/services/note_service.py config/seeds/prompts/note_update.yaml tests/integration/test_note_updater.py
git commit -m "feat(agents): NoteUpdater + @trigger declaration + NoteService"
```

---

### Task D3: InGroupResponder

**Depends on:** D0, D1
**Files:**
- Create: `src/agents/in_group_responder.py`
- Create: `config/seeds/prompts/in_group.yaml`
- Test: `tests/integration/test_in_group_responder.py`

**Acceptance:**
- [ ] Subscribe `message.captured` với `when=chat_type==group AND mentions_bot`
- [ ] Quick-ack pattern: predict long → ack first
- [ ] Reply trong cùng nhóm
- [ ] Reuse `run_agent` từ D1

**Steps:**

- [ ] **Step 1: Operation**

```python
# src/agents/in_group_responder.py
from dataclasses import dataclass
from src.agents.registry import operation
from src.agents.agent_loop import run_agent
from src.services.outbound_service import OutboundService
from src.llm.base import LLMRequest, ChatMessage

@dataclass
class InGroupCtx:
    boss: any
    memory: any
    retriever_factory: any
    llm: any
    bus: any
    db: any

@operation(
    name="in_group_responder",
    triggered_by=["message.captured"],
    when=lambda e: e.get("chat_type")=="group" and e.get("mentions_bot") is True,
    deps_type=InGroupCtx,
    prompt_key="in_group", feature="qa_with_search",
    memory_scopes=["semantic","episodic"],
    tools={"search_history","read_group_note","refresh_group_note","find_exact_quote",
           "set_reminder","list_reminders","pin_message","list_action_items",
           "mark_action_item","fetch_url","remember","current_time"},
    timeout_s=20, progress_mode="quick_ack",
    cache_prefix_hint="after_group_note",
)
class InGroupResponder:
    async def handle(self, event, ctx: InGroupCtx):
        outbound = OutboundService(ctx.db, ctx.bus)
        text = event.get("text","")
        # Quick ack if message > 60 chars (heuristic)
        if len(text) > 60:
            await outbound.send(boss_id=ctx.boss.id, provider=event["provider"],
                                chat_id=event["chat_id"], content="Để em xem...",
                                trigger="quick_ack")
        answer = await run_agent(InGroupResponder, event, ctx)
        await outbound.send(boss_id=ctx.boss.id, provider=event["provider"],
                            chat_id=event["chat_id"], content=answer, trigger="mention")
```

- [ ] **Step 2: Prompt + Test + Commit**

```yaml
# config/seeds/prompts/in_group.yaml
key: in_group
version: 1
is_active: true
body: |
  Em là thư ký của sếp {{ boss.name or 'anh' }}, đang được tag trong nhóm "{{ group_name }}".
  Trả lời ngắn, đúng trọng tâm, văn phong thư ký (không AI-themed).
  Tiếng Việt mặc định. KHÔNG emoji.
  Khi cần lịch sử nhóm, dùng `search_history` với `group_id={{ chat_id }}`.
  Khi sếp giao việc trong nhóm, gọi `set_reminder` scope=group, target_chat_id={{ chat_id }}.
```

```bash
git add src/agents/in_group_responder.py config/seeds/prompts/in_group.yaml tests/integration/test_in_group_responder.py
git commit -m "feat(agents): InGroupResponder + quick-ack pattern"
```

---

### Task D4: ReminderFirer

**Depends on:** D0, D1, A5 (reminders repo)
**Files:**
- Create: `src/agents/reminder_firer.py`
- Create: `src/services/reminder_service.py`
- Test: `tests/integration/test_reminder_firer.py`

**Acceptance:**
- [ ] Subscribe `reminder.due` event (publish bởi scheduler ở Batch F)
- [ ] Format text reminder; send tới `chat_id`; mark fired; tạo next occurrence nếu recurring
- [ ] Idempotent: fire 2 lần không gửi 2 lần (DB CHECK constraint hoặc status update trước send)

**Steps:**

- [ ] **Step 1: ReminderService**

```python
# src/services/reminder_service.py
from datetime import datetime, timedelta
class ReminderService:
    def __init__(self, pool, bus):
        self.pool = pool; self.bus = bus

    async def create(self, boss_id, text, due_at, scope, chat_id, recurring, created_by_op):
        async with self.pool.acquire() as c:
            rid = await c.fetchval("""
              INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, chat_id,
                                               recurring, created_by_op, status)
              VALUES ($1,$2,$3,$4,$5,$6,$7,'pending') RETURNING id
            """, boss_id, text, due_at, scope, chat_id, recurring, created_by_op)
        await self.bus.publish("reminder.set", {"reminder_id": rid, "boss_id": boss_id,
                                                "due_at": due_at.isoformat()})
        return rid

    async def fetch_due(self, now):
        async with self.pool.acquire() as c:
            return await c.fetch("""
              SELECT * FROM scheduled_reminders
              WHERE status='pending' AND due_at <= $1 LIMIT 50
            """, now)

    async def mark_fired(self, rid):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE scheduled_reminders SET status='fired', fired_at=NOW() WHERE id=$1", rid)

    async def mark_failed(self, rid, err):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE scheduled_reminders SET status='failed', last_error=$2 WHERE id=$1", rid, err)

    async def create_next(self, r):
        # parse recurring
        if r["recurring"] == "daily":
            next_due = r["due_at"] + timedelta(days=1)
        elif r["recurring"] and r["recurring"].startswith("weekly:"):
            # next from days list
            ...   # full impl in execution
        else:
            return
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, chat_id,
                                                                recurring, created_by_op, status)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,'pending')""",
                            r["boss_id"], r["text"], next_due, r["scope"], r["chat_id"],
                            r["recurring"], r["created_by_op"])
```

- [ ] **Step 2: ReminderFirer**

```python
# src/agents/reminder_firer.py
from dataclasses import dataclass
from src.agents.registry import operation
from src.services.outbound_service import OutboundService
from src.services.reminder_service import ReminderService

@dataclass
class FirerCtx:
    boss: any
    db: any
    bus: any

@operation(
    name="reminder_firer",
    triggered_by=["reminder.due"],
    when=None,
    deps_type=FirerCtx,
    prompt_key="", feature="",   # no LLM
    memory_scopes=[], tools=set(),
    timeout_s=10, progress_mode="none", max_concurrency_per_bot_account=10,
)
class ReminderFirer:
    async def handle(self, event, ctx: FirerCtx):
        rid = event["reminder_id"]
        async with ctx.db.acquire() as c:
            r = await c.fetchrow("SELECT * FROM scheduled_reminders WHERE id=$1 AND status='pending' FOR UPDATE", rid)
            if not r:
                return  # already fired or cancelled
            await c.execute("UPDATE scheduled_reminders SET status='fired', fired_at=NOW() WHERE id=$1", rid)
        out = OutboundService(ctx.db, ctx.bus)
        try:
            await out.send(boss_id=ctx.boss.id, provider=r["provider"] or "zalo",
                          chat_id=r["chat_id"], content=f"Nhắc anh: {r['text']}",
                          trigger="scheduled")
        except Exception as e:
            async with ctx.db.acquire() as c:
                await c.execute("UPDATE scheduled_reminders SET status='failed', last_error=$2 WHERE id=$1", rid, str(e))
            return
        if r["recurring"]:
            await ReminderService(ctx.db, ctx.bus).create_next(r)
```

- [ ] **Step 3: Commit**

```bash
git add src/agents/reminder_firer.py src/services/reminder_service.py tests/integration/test_reminder_firer.py
git commit -m "feat(agents): ReminderFirer + ReminderService (recurring, idempotent)"
```

---

## Batch E — Channel + bot account

Sau Batch A + D (cần OutboundService). **BLOCK bởi Task 0 spike.**

### Task E1: Zalo channel adapter (Python wrapper over Node bridge)

**Depends on:** Task 0 (spike GO), A, D
**Files:**
- Create: `src/channels/__init__.py`, `base.py`, `capabilities.py`
- Create: `src/channels/zalo/__init__.py`
- Create: `src/channels/zalo/adapter.py` (Python wrapper subprocess)
- Create: `src/channels/zalo/bridge_protocol.py` (JSONL command/event spec)
- Copy: `src/channels/zalo/bridge/` ← `spikes/zalo-2026/*.js` (login.js, bridge.js, send.js, package.json)
- Create: `src/channels/zalo/inbound_filter.py` (port từ legacy — filter forward, self-message)
- Create: `src/channels/zalo/markdown_strip.py` (port từ legacy)
- Test: `tests/integration/test_zalo_adapter.py` (record/replay JSONL fixture)

**Acceptance:**
- [ ] `ChannelAdapter` Protocol: `start_inbound(bot_acc)`, `send_text(bot_acc, chat_id, text, thread_kind)`, `list_members(bot_acc, group_id)`
- [ ] ZaloAdapter spawn `node bridge.js` subprocess per bot_account, read JSONL stdout → publish `inbound.raw.zalo` events
- [ ] Send via JSONL stdin command `{cmd:"send", chat_id, text, thread_kind}`
- [ ] Capabilities matrix declared (`zalo.requires_admin_role_for_core = False`)
- [ ] Subscriber on `inbound.raw.zalo` → normalize → publish `message.captured`

**Steps:**

- [ ] **Step 1: ChannelAdapter Protocol**

```python
# src/channels/base.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class InboundMessage:
    bot_account_id: int
    provider: str
    chat_id: str
    chat_type: str           # 'dm' | 'group'
    provider_msg_id: str | None
    sender_provider_id: str | None
    sender_name: str | None
    text: str
    mentions_bot: bool
    reply_to_provider_msg_id: str | None
    media_kind: str | None
    media_url: str | None
    ts: any

class ChannelAdapter(Protocol):
    provider: str
    async def start_inbound(self, bot_acc) -> None: ...
    async def stop_inbound(self, bot_acc) -> None: ...
    async def send_text(self, bot_acc, chat_id: str, text: str, thread_kind: str) -> str: ...
    async def list_members(self, bot_acc, group_id: str) -> list[str]: ...

# src/channels/capabilities.py
ZALO_CAPS = {
    "inbound.has_webhook": False,
    "inbound.supports_groups": True,
    "inbound.supports_mentions": True,
    "inbound.media_kinds": ["text","image","file","voice","sticker","url"],
    "outbound.send_text": True,
    "outbound.reply_to_msg": True,
    "outbound.send_file": True,
    "outbound.typing_indicator": True,
    "member.list_api": "partial",
    "auth.kind": "personal_cookies",
    "requires_admin_role_for_core": False,
}
```

- [ ] **Step 2: ZaloAdapter — subprocess management**

```python
# src/channels/zalo/adapter.py
import asyncio, json, os, signal, tempfile
from pathlib import Path
from src.channels.base import InboundMessage
from src.events.bus import EventBus
from cryptography.fernet import Fernet
from src.config import settings

BRIDGE_DIR = Path(__file__).parent / "bridge"
_fernet = Fernet(settings.FERNET_KEY.encode())

class ZaloAdapter:
    provider = "zalo"

    def __init__(self, bus: EventBus, bot_accounts_repo):
        self.bus = bus
        self.repo = bot_accounts_repo
        self._procs: dict[int, asyncio.subprocess.Process] = {}
        self._sessions_dir = Path(tempfile.mkdtemp(prefix="zalo_session_"))

    async def start_inbound(self, bot_acc):
        # Decrypt credentials → write to session.json in temp dir
        session_path = self._sessions_dir / f"{bot_acc.id}.json"
        creds = json.loads(_fernet.decrypt(bytes(bot_acc.credentials_blob_enc)))
        session_path.write_text(json.dumps(creds))

        env = os.environ.copy()
        env["SESSION_PATH"] = str(session_path)
        proc = await asyncio.create_subprocess_exec(
            "node", str(BRIDGE_DIR / "bridge.js"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BRIDGE_DIR), env=env,
        )
        self._procs[bot_acc.id] = proc
        asyncio.create_task(self._read_loop(bot_acc, proc))
        asyncio.create_task(self._read_stderr(bot_acc, proc))

    async def _read_loop(self, bot_acc, proc):
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "inbound":
                # publish raw, normalizer subscribed converts to message.captured
                await self.bus.publish("inbound.raw.zalo", {
                    "bot_account_id": bot_acc.id, "data": ev["data"],
                    "own_uid": ev.get("own_uid"),
                })
            elif ev.get("type") == "status":
                await self.bus.publish("bot_account.status_changed", {
                    "bot_account_id": bot_acc.id, "to": ev.get("status"),
                    "reason": ev.get("reason"),
                })

    async def _read_stderr(self, bot_acc, proc):
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            # log to structlog
            ...

    async def stop_inbound(self, bot_acc):
        proc = self._procs.pop(bot_acc.id, None)
        if proc:
            proc.send_signal(signal.SIGTERM)
            await proc.wait()

    async def send_text(self, bot_acc, chat_id, text, thread_kind):
        proc = self._procs[bot_acc.id]
        cmd = json.dumps({"cmd":"send","chat_id":chat_id,"text":text,"thread_kind":thread_kind}) + "\n"
        proc.stdin.write(cmd.encode())
        await proc.stdin.drain()
        # Bridge sends back {type:"send_ack", id:...} via stdout, parsed by _read_loop;
        # For MVP fire-and-forget, return placeholder
        return "<async>"

    async def list_members(self, bot_acc, group_id):
        proc = self._procs[bot_acc.id]
        cmd = json.dumps({"cmd":"fetch_members","group_id":group_id}) + "\n"
        proc.stdin.write(cmd.encode())
        await proc.stdin.drain()
        # Read until matching response — MVP simplification: wait for next "members" event
        # Full impl uses request ID matching
        ...
```

- [ ] **Step 3: Bridge.js — extend cho cmd send/fetch_members + status events**

Cập nhật `src/channels/zalo/bridge/bridge.js`: thêm stdin command loop (đọc JSONL từ stdin → dispatch send/fetch_members), thêm status event publish khi disconnect/banned.

(Code có sẵn ở legacy `archive/legacy:src/channels/zalo_bridge/bridge.js` — review + adapt cho protocol mới.)

- [ ] **Step 4: Normalizer subscriber**

```python
# src/channels/zalo/normalizer.py
from datetime import datetime, timezone
from src.repositories.account_links import AccountLinksRepo
from src.repositories.bot_account_assignments import BotAccountAssignmentsRepo
from src.repositories.messages import MessagesRepo
from src.repositories.base import BossContext
from src.channels.zalo.inbound_filter import should_drop
from src.channels.zalo.markdown_strip import strip_markdown

def register(bus, pool):
    async def handle(payload):
        data = payload["data"]
        bot_acc_id = payload["bot_account_id"]
        own_uid = payload["own_uid"]
        if should_drop(data):
            return
        # Determine chat_type
        chat_type = "dm" if data.get("type") == 0 else "group"
        thread_id = data["threadId"]
        text = data.get("content","") if isinstance(data.get("content"), str) else data["content"].get("title","")
        mentions = data.get("mentions", [])
        mentions_bot = any(m["uid"] == own_uid for m in mentions)
        sender_uid = data["uidFrom"]
        # Resolve boss_id: look up account_links + assignment
        async with pool.acquire() as c:
            link = await c.fetchrow("""
              SELECT al.boss_id FROM account_links al
              JOIN bot_account_assignments baa ON baa.boss_id = al.boss_id AND baa.provider = al.provider
              WHERE al.provider = 'zalo' AND al.provider_user_id = $1
                AND baa.bot_account_id = $2 AND baa.status = 'active'
            """, sender_uid if chat_type == "dm" else None, bot_acc_id)
        # For group: find any boss in this group assigned to this bot_acc
        if chat_type == "group":
            # ... (resolve via members list — punt to GroupOwnerResolver, Batch F)
            pass
        if not link:
            return
        boss_id = link["boss_id"]
        # Insert message
        repo = MessagesRepo(pool, BossContext(boss_id, "boss"))
        msg_id = await repo.insert(...)  # full insert from data
        # Publish message.captured
        await bus.publish("message.captured", {
            "message_id": msg_id, "boss_id": boss_id, "provider": "zalo",
            "chat_id": thread_id, "chat_type": chat_type,
            "mentions_bot": mentions_bot,
            "sender_is_boss": chat_type=="dm" and sender_uid == link.get("provider_user_id"),
            "text": text, "bot_account_id": bot_acc_id,
        })
    bus.subscribe("inbound.raw.zalo", handle)
```

- [ ] **Step 5: Outbound subscriber**

```python
# src/channels/zalo/outbound.py
def register(bus, adapter, pool, bot_accounts_repo):
    async def handle(payload):
        # Resolve which bot_acc to use
        boss_id = payload["boss_id"]
        async with pool.acquire() as c:
            row = await c.fetchrow("""
              SELECT ba.* FROM bot_accounts ba
              JOIN bot_account_assignments baa ON baa.bot_account_id = ba.id
              WHERE baa.boss_id=$1 AND baa.provider='zalo' AND baa.status='active'
            """, boss_id)
        if not row:
            return
        bot_acc = _row_to_bot_account(row)
        thread_kind = "group" if "@g" in payload["chat_id"] or len(payload["chat_id"])>15 else "user"  # heuristic
        await adapter.send_text(bot_acc, payload["chat_id"], payload["content"], thread_kind)
        # log outbound
        async with pool.acquire() as c:
            await c.execute("""
              INSERT INTO outbound_messages (boss_id, provider, chat_id, content, trigger, status)
              VALUES ($1,'zalo',$2,$3,$4,'sent')
            """, boss_id, payload["chat_id"], payload["content"], payload["trigger"])
    bus.subscribe("outbound.send", handle)
```

- [ ] **Step 6: Wire vào lifespan**

```python
# src/main.py
from src.channels.zalo.adapter import ZaloAdapter
from src.channels.zalo import normalizer, outbound

# in lifespan:
app.state.zalo = ZaloAdapter(app.state.bus, BotAccountsRepo(app.state.db_pool))
normalizer.register(app.state.bus, app.state.db_pool)
outbound.register(app.state.bus, app.state.zalo, app.state.db_pool, BotAccountsRepo(app.state.db_pool))
# Boot all bot accounts
async with app.state.db_pool.acquire() as c:
    rows = await c.fetch("SELECT * FROM bot_accounts WHERE provider='zalo' AND status='active'")
    for r in rows:
        await app.state.zalo.start_inbound(_row_to_bot_account(r))
```

- [ ] **Step 7: Commit**

```bash
git add src/channels/ tests/integration/test_zalo_adapter.py src/main.py
git commit -m "feat(channel): Zalo adapter (Node bridge subprocess) + normalizer + outbound"
```

---

### Task E2: Bot account management (lifecycle, dual-mode)

**Depends on:** A5 (bot_accounts repo), E1 (adapter to call session login)
**Files:**
- Create: `src/services/bot_account_service.py` (auto_assign, accept, decline, switch_mode, disable)
- Create: `src/services/bot_account_session.py` (encrypt creds, login flow wrapper)
- Test: `tests/integration/test_bot_account_service.py`

**Acceptance:**
- [ ] `auto_assign(boss_id, provider)` pick least-loaded platform acc → status=pending_accept
- [ ] `accept(boss_id, provider)` → status=active + start_inbound (if not running)
- [ ] `decline(boss_id, provider)` → status=rejected + free slot
- [ ] `switch_mode(boss_id, target_mode)` revoke current + start new flow (xem §3.10)
- [ ] `disable_boss_owned(bot_acc_id, reason, by_user_id)` → status=paused + audit log
- [ ] Constraint check: ownership='platform' → cap; ownership='boss_owned' → 1 sếp duy nhất

**Steps:**

- [ ] **Step 1: BotAccountService skeleton**

```python
# src/services/bot_account_service.py
from src.repositories.bot_accounts import BotAccountsRepo
from src.repositories.bot_account_assignments import BotAccountAssignmentsRepo
from src.repositories.admin_audit_log import AdminAuditLogRepo

class BotAccountService:
    def __init__(self, pool, bus, adapter_map):
        self.pool = pool; self.bus = bus
        self.adapters = adapter_map   # {"zalo": ZaloAdapter, ...}

    async def auto_assign(self, boss_id, provider):
        async with self.pool.acquire() as c:
            row = await c.fetchrow("""
              SELECT ba.* FROM bot_accounts ba
              LEFT JOIN bot_account_assignments baa
                ON baa.bot_account_id = ba.id AND baa.status='active'
              WHERE ba.provider=$1 AND ba.ownership='platform' AND ba.status='active'
              GROUP BY ba.id
              HAVING count(baa.boss_id) < ba.max_assigned_bosses
              ORDER BY count(baa.boss_id), ba.msgs_received_total
              LIMIT 1
            """, provider)
            if not row:
                raise LookupError(f"no capacity for provider={provider}")
            await c.execute("""
              INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id,
                                                   assignment_kind, status, assigned_by)
              VALUES ($1,$2,$3,'platform_assigned','pending_accept', NULL)
              ON CONFLICT (boss_id, provider) DO UPDATE SET
                bot_account_id=EXCLUDED.bot_account_id, status='pending_accept', assigned_at=NOW()
            """, boss_id, provider, row["id"])
            return row["id"]

    async def accept(self, boss_id, provider):
        async with self.pool.acquire() as c:
            await c.execute("""
              UPDATE bot_account_assignments SET status='active', accepted_at=NOW()
              WHERE boss_id=$1 AND provider=$2 AND status='pending_accept'
            """, boss_id, provider)
            row = await c.fetchrow("""
              SELECT ba.* FROM bot_accounts ba
              JOIN bot_account_assignments baa ON baa.bot_account_id=ba.id
              WHERE baa.boss_id=$1 AND baa.provider=$2
            """, boss_id, provider)
        adapter = self.adapters[provider]
        # Ensure inbound running for this bot_acc (idempotent)
        await adapter.start_inbound(_row_to_bot_account(row))

    async def decline(self, boss_id, provider, reason: str | None = None):
        async with self.pool.acquire() as c:
            await c.execute("""
              UPDATE bot_account_assignments SET status='rejected', accepted_at=NULL
              WHERE boss_id=$1 AND provider=$2 AND status='pending_accept'
            """, boss_id, provider)

    async def disable_boss_owned(self, bot_acc_id, reason, by_user_id):
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM bot_accounts WHERE id=$1", bot_acc_id)
            if row["ownership"] != "boss_owned":
                raise ValueError("only boss_owned can be disabled this way")
            await c.execute("UPDATE bot_accounts SET status='paused', status_reason=$2 WHERE id=$1", bot_acc_id, reason)
            await c.execute("""
              INSERT INTO admin_audit_log (actor_user_id, action, target_kind, target_id, reason, payload_json)
              VALUES ($1, 'disable_boss_owned_bot_acc', 'bot_account', $2, $3, '{}'::jsonb)
            """, by_user_id, str(bot_acc_id), reason)
        # Stop inbound (without reading credentials)
        adapter = self.adapters[row["provider"]]
        bot_acc = _row_to_bot_account(row)
        await adapter.stop_inbound(bot_acc)

    async def switch_mode(self, boss_id, provider, target_mode):
        # ... revoke current assignment, start new wizard. Web routes handle UI flow.
        ...
```

- [ ] **Step 2: Session encryption helper**

```python
# src/services/bot_account_session.py
import json
from cryptography.fernet import Fernet
from src.config import settings

_fernet = Fernet(settings.FERNET_KEY.encode())

def encrypt_credentials(session: dict) -> bytes:
    return _fernet.encrypt(json.dumps(session).encode())

def decrypt_credentials(blob: bytes) -> dict:
    return json.loads(_fernet.decrypt(bytes(blob)))
```

- [ ] **Step 3: Test + Commit**

```bash
git add src/services/bot_account_service.py src/services/bot_account_session.py tests/integration/test_bot_account_service.py
git commit -m "feat(bot_accounts): service — auto_assign + accept + disable + audit log"
```

---

### Task E3: Linking flow (account_links + linking_tokens + accept handshake)

**Depends on:** E1, E2
**Files:**
- Create: `src/services/linking_service.py`
- Create: `src/web/routes/channels.py` (`/channels`, `/channels/accept`, `/channels/decline`)
- Test: `tests/integration/test_linking_flow.py`

**Acceptance:**
- [ ] `generate_token(boss_id, provider, bot_acc_id)` → secret 16-byte token, TTL 10 phút
- [ ] `consume_token(token, sender_uid, bot_acc_id)` validate + INSERT `account_links` + DELETE token
- [ ] Inbound DM listener detect `/start <token>` → invoke `consume_token`
- [ ] Web flow: web shows token; sếp gửi DM trên Zalo; web auto-refresh (poll `/channels`)

**Steps:**

- [ ] **Step 1: LinkingService**

```python
# src/services/linking_service.py
import secrets, datetime
class LinkingService:
    def __init__(self, pool):
        self.pool = pool

    async def generate(self, boss_id, provider, bot_account_id):
        token = secrets.token_urlsafe(16)
        async with self.pool.acquire() as c:
            await c.execute("""
              INSERT INTO linking_tokens (token, boss_id, provider, bot_account_id, expires_at)
              VALUES ($1,$2,$3,$4, NOW() + INTERVAL '10 minutes')
            """, token, boss_id, provider, bot_account_id)
        return token

    async def consume(self, token, sender_provider_uid, bot_account_id):
        async with self.pool.acquire() as c:
            row = await c.fetchrow("""
              SELECT * FROM linking_tokens WHERE token=$1 AND expires_at > NOW()
            """, token)
            if not row or row["bot_account_id"] != bot_account_id:
                return None
            await c.execute("""
              INSERT INTO account_links (boss_id, provider, provider_user_id)
              VALUES ($1,$2,$3) ON CONFLICT DO NOTHING
            """, row["boss_id"], row["provider"], sender_provider_uid)
            await c.execute("DELETE FROM linking_tokens WHERE token=$1", token)
            return row["boss_id"]
```

- [ ] **Step 2: Inbound subscriber detect `/start <token>`**

```python
# src/channels/zalo/normalizer.py — extend
async def handle(payload):
    data = payload["data"]
    bot_acc_id = payload["bot_account_id"]
    # ... existing logic ...
    text = data.get("content","") if isinstance(data.get("content"), str) else ""
    if data.get("type") == 0 and text.startswith("/start "):
        token = text.split(" ", 1)[1].strip()
        from src.services.linking_service import LinkingService
        boss_id = await LinkingService(pool).consume(token, data["uidFrom"], bot_acc_id)
        if boss_id:
            await bus.publish("outbound.send", {
                "boss_id": boss_id, "provider": "zalo",
                "chat_id": data["uidFrom"], "content": "Đã kết nối. Em là bot của anh ở đây.",
                "trigger": "system",
            })
        return
    # ... rest of normalize logic
```

- [ ] **Step 3: Commit (web routes ở Task G3)**

```bash
git add src/services/linking_service.py src/channels/zalo/normalizer.py tests/integration/test_linking_flow.py
git commit -m "feat(linking): generate + consume linking_token + /start detect in inbound"
```

---

## Batch F — Scheduler + media + plugin scaffold

Sau Batch D. F1 ↔ F2 ↔ F3 parallel.

### Task F1: APScheduler jobs (reminder firer, note flush, health check, subscription check)

**Depends on:** D2 (note service), D4 (reminder service), E2 (bot account service)
**Files:**
- Create: `src/scheduler/__init__.py`, `runner.py`
- Create: `src/scheduler/jobs/note_flush.py` (defer — TriggerEngine debounce đã handle; chỉ retry stuck locks)
- Create: `src/scheduler/jobs/reminder_firer.py` (publish `reminder.due` mỗi 30s)
- Create: `src/scheduler/jobs/bot_account_health.py` (mỗi 60s — ping bridge, mark logged_out)
- Create: `src/scheduler/jobs/subscription_check.py` (hàng ngày — expire stale subs)
- Test: `tests/integration/test_scheduler_jobs.py`

**Acceptance:**
- [ ] APScheduler khởi động cùng FastAPI lifespan
- [ ] Reminder firer publish event đúng lịch
- [ ] Bot account health publish `bot_account.status_changed` khi process chết
- [ ] Subscription check update `users.subscription_status` khi expiry < NOW

**Steps:**

- [ ] **Step 1: Scheduler runner**

```python
# src/scheduler/runner.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

def make_scheduler(app_state):
    sched = AsyncIOScheduler(timezone="UTC")
    from src.scheduler.jobs.reminder_firer import job as remind_job
    from src.scheduler.jobs.bot_account_health import job as health_job
    from src.scheduler.jobs.subscription_check import job as sub_job
    sched.add_job(lambda: remind_job(app_state), "interval", seconds=30, id="reminder_firer")
    sched.add_job(lambda: health_job(app_state), "interval", seconds=60, id="bot_account_health")
    sched.add_job(lambda: sub_job(app_state), "cron", hour=2, id="subscription_check")
    return sched
```

- [ ] **Step 2: reminder_firer job**

```python
# src/scheduler/jobs/reminder_firer.py
from datetime import datetime, timezone
async def job(app_state):
    now = datetime.now(timezone.utc)
    async with app_state.db_pool.acquire() as c:
        rows = await c.fetch("""
          SELECT id, boss_id FROM scheduled_reminders
          WHERE status='pending' AND due_at <= $1 LIMIT 50
        """, now)
    for r in rows:
        await app_state.bus.publish("reminder.due", {"reminder_id": r["id"], "boss_id": r["boss_id"]})
```

- [ ] **Step 3: bot_account_health job**

```python
# src/scheduler/jobs/bot_account_health.py
async def job(app_state):
    # For each running adapter, check subprocess alive
    for bot_acc_id, proc in list(app_state.zalo._procs.items()):
        if proc.returncode is not None:
            # Process died
            async with app_state.db_pool.acquire() as c:
                await c.execute("UPDATE bot_accounts SET status='logged_out' WHERE id=$1", bot_acc_id)
            await app_state.bus.publish("bot_account.status_changed", {
                "bot_account_id": bot_acc_id, "to": "logged_out", "reason": "process_died",
            })
            app_state.zalo._procs.pop(bot_acc_id, None)
```

- [ ] **Step 4: subscription_check**

```python
# src/scheduler/jobs/subscription_check.py
async def job(app_state):
    async with app_state.db_pool.acquire() as c:
        await c.execute("""
          UPDATE users SET subscription_status='expired_grace'
          WHERE subscription_status='active' AND subscription_expiry < NOW()
        """)
        await c.execute("""
          UPDATE users SET subscription_status='expired'
          WHERE subscription_status='expired_grace'
            AND subscription_expiry < NOW() - INTERVAL '30 days'
        """)
```

- [ ] **Step 5: Wire vào lifespan**

```python
# src/main.py — in lifespan after registries:
app.state.scheduler = make_scheduler(app.state)
app.state.scheduler.start()
yield
app.state.scheduler.shutdown()
```

- [ ] **Step 6: Commit**

```bash
git add src/scheduler/ tests/integration/test_scheduler_jobs.py src/main.py
git commit -m "feat(scheduler): APScheduler jobs (reminder/health/sub)"
```

---

### Task F2: Media adapters (URL, YouTube, doc, image)

**Depends on:** B2 (LLM for image vision)
**Files:**
- Create: `src/media/__init__.py`, `base.py`, `registry.py`
- Create: `src/media/adapters/web.py` (URL extract via trafilatura + YouTube via yt-dlp + TikTok)
- Create: `src/media/adapters/document.py` (PDF/DOCX/XLSX/TXT)
- Create: `src/media/adapters/image.py` (HEIC convert + vision-LLM extract-once + cache)
- Test: `tests/integration/test_media_adapters.py`

**Acceptance:**
- [ ] `@media_adapter(supports={...}, priority=)` decorator
- [ ] Registry: `find_adapter(media_kind=, url=)` returns first matching
- [ ] URL: trafilatura extract body, max 50KB; YouTube: yt-dlp auto-caption
- [ ] Image: HEIC → JPEG (pillow_heif), filter sticker (<50KB, dim<200), vision-LLM extract description + OCR, cache by content sha256
- [ ] Document: PDF/DOCX/XLSX text extract, max 20 pages
- [ ] Cache: `media_cache` table — same URL/hash không re-fetch (TTL 30d for URL)

**Steps:**

- [ ] **Step 1: Base + registry**

```python
# src/media/base.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class MediaExtractResult:
    media_text: str
    title: str | None = None
    extra: dict | None = None

class MediaAdapter(Protocol):
    supports: set[str]
    priority: int
    async def extract(self, url: str | None = None, content: bytes | None = None,
                      content_type: str | None = None) -> MediaExtractResult: ...

# src/media/registry.py
_ADAPTERS: list[type] = []

def media_adapter(*, supports: set[str], priority: int = 10, requires_caps: set[str] = frozenset()):
    def deco(cls):
        cls.supports = supports; cls.priority = priority; cls.requires_caps = requires_caps
        _ADAPTERS.append(cls)
        return cls
    return deco

def find_adapter(media_kind: str | None = None, url: str | None = None):
    # Detect from URL if media_kind missing
    if url and not media_kind:
        media_kind = _detect_from_url(url)
    candidates = sorted([a for a in _ADAPTERS if media_kind in a.supports], key=lambda a: -a.priority)
    if not candidates:
        raise LookupError(f"no adapter for {media_kind}")
    return candidates[0]()

def _detect_from_url(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url: return "tiktok"
    return "url"
```

- [ ] **Step 2: Web adapter**

```python
# src/media/adapters/web.py
import httpx, trafilatura, yt_dlp
from src.media.registry import media_adapter
from src.media.base import MediaExtractResult

@media_adapter(supports={"url","youtube","tiktok"})
class WebExtractor:
    async def extract(self, url, content=None, content_type=None):
        if "youtube.com" in url or "youtu.be" in url:
            return await self._youtube(url)
        # Generic URL
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            extracted = trafilatura.extract(r.text, include_comments=False)
        return MediaExtractResult(media_text=extracted or "", title=_extract_title(r.text))

    async def _youtube(self, url):
        opts = {"skip_download": True, "writeautomaticsub": True, "subtitleslangs": ["vi","en"]}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        subtitle = _pick_subtitle(info)
        text = f"{info.get('title','')}\n\n{subtitle or info.get('description','')}"
        return MediaExtractResult(media_text=text[:50000], title=info.get("title"))
```

- [ ] **Step 3: Document adapter**

```python
# src/media/adapters/document.py
@media_adapter(supports={"pdf","docx","xlsx","txt"})
class DocumentExtractor:
    async def extract(self, url=None, content=None, content_type=None):
        # ...detect kind from content_type or extension, dispatch to pypdf/python-docx/openpyxl
        ...
```

- [ ] **Step 4: Image adapter (extract-once + cache)**

```python
# src/media/adapters/image.py
import hashlib, io
from PIL import Image
from pillow_heif import register_heif_opener
register_heif_opener()
from src.media.registry import media_adapter
from src.media.base import MediaExtractResult
from src.repositories.media_cache import MediaCacheRepo

@media_adapter(supports={"image"}, requires_caps={"vision"})
class ImageExtractor:
    def __init__(self, llm_gateway, pool):
        self.llm = llm_gateway; self.pool = pool

    async def extract(self, url=None, content=None, content_type=None):
        # Pull bytes
        if url and not content:
            import httpx
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(url); content = r.content
        # Filter sticker/icon
        if len(content) < 50_000:
            return MediaExtractResult(media_text="")
        # HEIC → JPEG
        img = Image.open(io.BytesIO(content))
        if img.size[0] < 200 or img.size[1] < 200:
            return MediaExtractResult(media_text="")
        # Cache by content hash
        h = hashlib.sha256(content).hexdigest()
        cache = MediaCacheRepo(self.pool)
        existing = await cache.get(h, "image")
        if existing:
            return MediaExtractResult(media_text=existing.media_text)
        # Save as JPEG buffer
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        # Vision-LLM extract
        from src.llm.base import LLMRequest, ChatMessage
        req = LLMRequest(
            feature="image_extract", boss_id=0,  # caller passes; for batch capture maybe boss=0 (system)
            messages=[ChatMessage(role="user", content=[
                {"type":"text","text":"Mô tả ngắn ảnh này (1–3 câu) và trích text nếu có (OCR). Bỏ qua sticker/meme."},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            ])],
            required_caps={"vision"}, routing_hints={"op":"image_extract"},
        )
        resp = await self.llm.complete(req)
        media_text = f"[image] {resp.content}"
        await cache.insert(h, "image", media_text, expires_at=None)
        return MediaExtractResult(media_text=media_text)
```

- [ ] **Step 5: Force imports**

```python
# src/media/__init__.py
from src.media.adapters import web, document, image  # noqa
```

- [ ] **Step 6: Commit**

```bash
git add src/media/ tests/integration/test_media_adapters.py
git commit -m "feat(media): URL/YouTube/document/image adapters + content-hash cache"
```

---

### Task F3: Plugin loader scaffold

**Depends on:** C1 (tool registry shared), A5 (boss_integrations repo)
**Files:**
- Create: `src/plugin_api/__init__.py` (re-export `@tool` từ `src.tools.registry` + `ToolContext`)
- Create: `src/plugins_loader.py` (scan `plugins/` dir, read manifest, import tools)
- Create: `plugins/.gitkeep` (workspace empty MVP)
- Test: `tests/integration/test_plugin_loader.py` (fixture plugin)

**Acceptance:**
- [ ] Loader scan `plugins/*/manifest.toml`
- [ ] Import `plugins.<name>.tools` qua `importlib.import_module`
- [ ] Tool decorator runs → registers vào shared `_REGISTRY`
- [ ] Per-boss filter: dispatcher `filter_for_op(op_name, allowed_tools)` chỉ list plugin tool nếu `boss_integrations.enabled`
- [ ] Test: drop fixture plugin in test dir → tools registered

**Steps:**

- [ ] **Step 1: plugin_api re-export**

```python
# src/plugin_api/__init__.py
from src.tools.registry import tool
from src.tools.base import ToolContext, ToolResult
__all__ = ["tool","ToolContext","ToolResult"]
```

- [ ] **Step 2: Loader**

```python
# src/plugins_loader.py
import importlib, logging, tomllib
from pathlib import Path

log = logging.getLogger(__name__)
PLUGINS_DIR = Path(__file__).parent.parent / "plugins"

def load_all():
    registered = []
    if not PLUGINS_DIR.exists():
        return registered
    for p in PLUGINS_DIR.iterdir():
        if not p.is_dir() or not (p / "manifest.toml").exists():
            continue
        manifest = tomllib.loads((p / "manifest.toml").read_text())
        name = p.name
        try:
            mod = importlib.import_module(f"plugins.{name}.tools")
            log.info("plugin loaded", extra={"plugin": name, "tools": manifest.get("capabilities",{}).get("tools",[])})
            registered.append(name)
        except Exception:
            log.exception("plugin load fail", extra={"plugin": name})
    return registered
```

- [ ] **Step 3: Wire vào lifespan**

```python
# src/main.py — in lifespan:
from src.plugins_loader import load_all
loaded = load_all()
log.info("plugins loaded", extra={"plugins": loaded})
```

- [ ] **Step 4: Per-boss filter trong agent_loop**

`agent_loop.py` đã filter tools qua `filter_for_op(op_name, allowed=cfg.tools)`. Plugin tools muốn enabled cho boss thì sửa:

```python
# src/agents/agent_loop.py — extend
async def _allowed_tools(cfg, ctx):
    base = set(cfg.tools)
    async with ctx.db.acquire() as c:
        rows = await c.fetch("""
          SELECT plugin_id FROM boss_integrations WHERE boss_id=$1 AND enabled=TRUE
        """, ctx.boss.id)
    enabled_plugins = {r["plugin_id"] for r in rows}
    # Plugin tools đặt tên `<plugin_id>_*` — auto-include nếu plugin enabled
    for t in _REGISTRY.values():
        if t.name.split("_",1)[0] in enabled_plugins:
            base.add(t.name)
    return base
```

- [ ] **Step 5: Commit**

```bash
git add src/plugin_api/ src/plugins_loader.py plugins/.gitkeep tests/integration/test_plugin_loader.py src/main.py
git commit -m "feat(plugins): loader scaffold + plugin_api re-export"
```

---

## Batch G — Web (auth + user pages + admin pages + settings)

Sau Batch A (auth deps). Parallel-safe với Batch C/D/E/F sau khi Batch A xong.

### Task G1: Web foundation — auth, session, CSRF, templates

**Depends on:** A1, A2, A5
**Files:**
- Create: `src/web/__init__.py`, `routes/__init__.py`, `routes/auth.py`, `routes/oauth.py`
- Create: `src/web/templates/base.html` (Jinja2 layout — Tailwind CDN MVP, swap built CSS Phase 1)
- Create: `src/web/templates/login.html`
- Create: `src/web/static/app.js` (HTMX setup)
- Create: `src/web/security.py` (CSRF token, session middleware)
- Modify: `src/main.py` (mount static, include routers)
- Test: `tests/integration/test_auth.py`

**Acceptance:**
- [ ] `/login` page render (Jinja2)
- [ ] Google OAuth flow: `/api/oauth/google/login` → redirect; `/api/oauth/google/callback` exchange code, lookup/create `users`, set session cookie
- [ ] Email/password fallback: form submit `/login` → bcrypt verify → session
- [ ] Session middleware (itsdangerous signed cookie, HttpOnly, Secure, SameSite=Lax)
- [ ] CSRF token meta tag + `X-CSRF-Token` validate cho POST `/api/*`
- [ ] Redirect whitelist exact match (`OAUTH_REDIRECT_WHITELIST`)
- [ ] Logged-in `request.state.boss` = `Boss` entity; superadmin gated by email

**Steps:**

- [ ] **Step 1: Session middleware**

```python
# src/web/security.py
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException
from src.config import settings
import secrets

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)
SESSION_COOKIE = "smart_session"
CSRF_COOKIE = "smart_csrf"
SESSION_TTL = 30 * 24 * 3600   # 30 days

def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})

def read_session(cookie: str | None) -> int | None:
    if not cookie: return None
    try:
        return _serializer.loads(cookie, max_age=SESSION_TTL)["uid"]
    except Exception:
        return None

def ensure_csrf(request: Request) -> str:
    tok = request.cookies.get(CSRF_COOKIE)
    if not tok:
        tok = secrets.token_urlsafe(16)
    return tok

def verify_csrf(request: Request):
    cookie_tok = request.cookies.get(CSRF_COOKIE)
    header_tok = request.headers.get("X-CSRF-Token")
    if not cookie_tok or cookie_tok != header_tok:
        raise HTTPException(403, "CSRF check failed")
```

- [ ] **Step 2: Auth dependency**

```python
# src/web/deps.py — extend
from src.repositories.users import UsersRepo
from src.repositories.base import BossContext

async def get_current_boss(request: Request):
    cookie = request.cookies.get(SESSION_COOKIE)
    uid = read_session(cookie)
    if not uid:
        raise HTTPException(401, "not logged in")
    pool = request.app.state.db_pool
    # MVP: role = boss; promote to superadmin if email in env
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM users WHERE id=$1", uid)
        if not row:
            raise HTTPException(401, "user not found")
        role = "superadmin" if row["email"].lower() in settings.superadmin_emails_set else row["role"]
    return BossContext(boss_id=uid, user_role=role)

async def require_superadmin(ctx = Depends(get_current_boss)):
    if ctx.user_role != "superadmin":
        raise HTTPException(403, "superadmin only")
    return ctx
```

- [ ] **Step 3: OAuth routes**

```python
# src/web/routes/oauth.py
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, HTTPException, Response
from src.config import settings
from src.web.security import make_session, SESSION_COOKIE, SESSION_TTL

router = APIRouter(prefix="/api/oauth")
oauth = OAuth()
oauth.register(name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=settings.GOOGLE_OAUTH_CLIENT_ID, client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
    client_kwargs={"scope":"openid email profile"})

@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = str(request.url_for("google_callback"))
    if redirect_uri not in settings.redirect_whitelist:
        raise HTTPException(400, "redirect not allowed")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, response: Response):
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo")
    if not info or not info.get("email_verified"):
        raise HTTPException(400, "email not verified")
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT id FROM users WHERE google_sub=$1 OR email=$2",
                                info["sub"], info["email"].lower())
        if row:
            uid = row["id"]
            await c.execute("UPDATE users SET google_sub=$1, name=$2 WHERE id=$3",
                            info["sub"], info.get("name"), uid)
        else:
            uid = await c.fetchval("""
              INSERT INTO users (email, name, google_sub, role) VALUES ($1,$2,$3,'boss') RETURNING id
            """, info["email"].lower(), info.get("name"), info["sub"])
    sess = make_session(uid)
    response.set_cookie(SESSION_COOKIE, sess, max_age=SESSION_TTL, httponly=True,
                       secure=request.url.scheme=="https", samesite="lax")
    response.headers["Location"] = "/app"; response.status_code = 302
    return response
```

- [ ] **Step 4: Templates base**

```html
<!-- src/web/templates/base.html -->
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <title>{% block title %}SMART_bot{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@2.0.3"></script>
  <script src="https://unpkg.com/alpinejs@3.14" defer></script>
  <script>
    htmx.on("htmx:configRequest", e => {
      e.detail.headers["X-CSRF-Token"] = document.querySelector('meta[name=csrf-token]').content;
    });
  </script>
</head>
<body class="bg-gray-50 text-gray-900 font-sans">
  {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Commit**

```bash
git add src/web/ tests/integration/test_auth.py src/main.py
git commit -m "feat(web): auth foundation — Google OAuth + session + CSRF + base template"
```

---

### Task G2: User pages (Dashboard, Groups, Notes, Reminders, Channels, Settings)

**Depends on:** G1, batches A–F (entities)
**Files:**
- Create: `src/web/routes/app.py` (`/`, `/groups`, `/groups/:id`, `/action-items`, `/projects`, `/reminders`, `/channels`, `/usage`, `/settings/general`, `/settings/account`, `/subscription`)
- Create: `src/web/routes/api.py` (HTMX partials: `/api/groups/:id/note`, `/api/reminders/list`, etc)
- Create: `src/web/templates/` (1 file per page)
- Create: `src/web/schemas/` (Pydantic DTOs)
- Test: `tests/integration/test_user_pages.py`

**Acceptance:**
- [ ] 11 route render 200 cho logged-in boss; 401 cho anonymous
- [ ] HTMX partials cho live update (note preview SSE chỉ Phase 1 — MVP polling 30s)
- [ ] CRUD reminder qua web form + tool agent

**Steps:**

- [ ] **Step 1: Route pattern**

```python
# src/web/routes/app.py
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from src.web.deps import get_current_boss
from src.web.security import ensure_csrf
from pathlib import Path

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
router = APIRouter()

def _ctx(request, boss_ctx):
    return {"request": request, "csrf_token": ensure_csrf(request), "boss_ctx": boss_ctx}

@router.get("/")
async def dashboard(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        groups = await c.fetchval("SELECT count(*) FROM group_notes WHERE boss_id=$1", ctx.boss_id)
        open_items = await c.fetchval("SELECT count(*) FROM action_items WHERE boss_id=$1 AND status='open'", ctx.boss_id)
        pending_rems = await c.fetchval("SELECT count(*) FROM scheduled_reminders WHERE boss_id=$1 AND status='pending'", ctx.boss_id)
    return templates.TemplateResponse("dashboard.html", _ctx(request, ctx) | {
        "groups_count": groups, "open_items": open_items, "pending_rems": pending_rems,
    })
```

- [ ] **Step 2: Pattern lặp cho 11 route** — mỗi route ~20 dòng. Subagent execute từng route 1.

- [ ] **Step 3: Templates** — Jinja2 + Tailwind utility class. Vd `groups.html`:

```html
{% extends "base.html" %}
{% block body %}
<div class="max-w-6xl mx-auto p-6">
  <h1 class="text-2xl font-semibold mb-4">Nhóm đã capture</h1>
  <table class="w-full border">
    <thead class="bg-gray-100 text-sm"><tr>
      <th class="p-2 text-left">Nhóm</th><th class="p-2">Update</th>
      <th class="p-2">Việc mở</th><th class="p-2">Trễ</th>
    </tr></thead>
    <tbody>
      {% for g in groups %}
      <tr class="border-t hover:bg-gray-50">
        <td class="p-2"><a href="/groups/{{ g.chat_id }}" class="text-blue-700">{{ g.group_name or g.chat_id }}</a></td>
        <td class="p-2">{{ g.updated_at.strftime('%d/%m %H:%M') }}</td>
        <td class="p-2 text-center">{{ g.open_count }}</td>
        <td class="p-2 text-center">{{ g.overdue_count }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Commit per ~3 page**

```bash
git add src/web/routes/app.py src/web/templates/ src/web/schemas/
git commit -m "feat(web): user pages — dashboard + groups + group detail"
git commit -m "feat(web): user pages — reminders + projects + channels"
git commit -m "feat(web): user pages — settings + subscription + usage"
```

---

### Task G3: Admin pages (Bosses, Bot Accounts, Models, Prompts, Templates, Routes, Budgets, Triggers, Pipelines, Audit Log)

**Depends on:** G1, E2 (bot account service)
**Files:**
- Create: `src/web/routes/admin.py`
- Create: `src/web/templates/admin/` (10+ pages)
- Test: `tests/integration/test_admin_pages.py`

**Acceptance:**
- [ ] All `/admin/*` routes require `require_superadmin`
- [ ] CRUD UI cho `models`, `prompts`, `note_templates`, `llm_routes`, `feature_budgets`, `agent_triggers`, `retrieval_pipelines`
- [ ] Bot accounts page: tab Platform / Boss-owned, per-acc detail + auto-assign button
- [ ] Each CRUD mutation publish `registry.invalidated` event
- [ ] Audit log page: list `admin_audit_log` rows

**Steps:**

- [ ] **Step 1: Bosses page**

```python
# src/web/routes/admin.py
@router.get("/admin/bosses")
async def admin_bosses(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        bosses = await c.fetch("""
          SELECT u.*, ba.provider, ba.id AS bot_acc_id
          FROM users u
          LEFT JOIN bot_account_assignments baa ON baa.boss_id = u.id AND baa.status='active'
          LEFT JOIN bot_accounts ba ON ba.id = baa.bot_account_id
          WHERE u.role='boss' ORDER BY u.created_at DESC
        """)
    return templates.TemplateResponse("admin/bosses.html", _ctx(request, ctx) | {"bosses": bosses})

@router.post("/admin/bosses/{boss_id}/assign-zalo")
async def admin_assign(boss_id: int, request: Request, ctx=Depends(require_superadmin)):
    verify_csrf(request)
    svc = BotAccountService(request.app.state.db_pool, request.app.state.bus,
                            {"zalo": request.app.state.zalo})
    await svc.auto_assign(boss_id, "zalo")
    return RedirectResponse("/admin/bosses", status_code=303)
```

- [ ] **Step 2: Bot accounts page (Platform + Boss-owned tabs)**

```python
@router.get("/admin/bot-accounts")
async def admin_bot_accounts(request: Request, tab: str = "platform", ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch("""
          SELECT ba.*,
                 (SELECT COUNT(*) FROM bot_account_assignments WHERE bot_account_id=ba.id AND status='active') AS active_assignments,
                 (SELECT COUNT(*) FROM messages WHERE provider=ba.provider
                  AND ingested_at > NOW()-INTERVAL '7 days') AS msgs_7d
          FROM bot_accounts ba WHERE ba.ownership=$1 ORDER BY ba.created_at DESC
        """, "platform" if tab=="platform" else "boss_owned")
    return templates.TemplateResponse("admin/bot_accounts.html", _ctx(request, ctx) | {
        "rows": rows, "tab": tab,
    })
```

- [ ] **Step 3: Models / Prompts / Routes / Budgets / Triggers / Pipelines CRUD**

Pattern: GET list (table); GET detail (form); POST update → INSERT/UPDATE → publish `registry.invalidated` → redirect.

```python
@router.post("/admin/llm-routes/{route_id}")
async def admin_update_route(route_id: int, request: Request, ctx=Depends(require_superadmin)):
    verify_csrf(request)
    form = await request.form()
    async with request.app.state.db_pool.acquire() as c:
        await c.execute("""
          UPDATE llm_routes SET target_tier=$2, fallback_chain=$3::jsonb, weight=$4, is_active=$5, updated_at=NOW()
          WHERE id=$1
        """, route_id, form["target_tier"], form["fallback_chain"],
            int(form["weight"]), form.get("is_active") == "on")
    await request.app.state.bus.publish("registry.invalidated",
        {"registry_name":"llm_routes","key":str(route_id),"by_user_id":ctx.boss_id})
    return RedirectResponse("/admin/llm-routes", status_code=303)
```

- [ ] **Step 4: Audit log**

```python
@router.get("/admin/audit-log")
async def audit_log(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch("SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT 200")
    return templates.TemplateResponse("admin/audit_log.html", _ctx(request, ctx) | {"rows": rows})
```

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/admin.py src/web/templates/admin/
git commit -m "feat(web): admin pages — bosses + bot accounts + models + prompts"
git commit -m "feat(web): admin pages — llm_routes + feature_budgets + triggers + pipelines + audit"
```

---

### Task G4: Settings AI (3 model slot + BYO API keys + cost cap)

**Depends on:** G1, A5 (users repo)
**Files:**
- Modify: `src/web/routes/app.py` (add `/settings/ai`)
- Create: `src/web/templates/settings_ai.html`
- Create: `src/web/routes/api_ai.py` (`/api/ai/test-key`)
- Test: `tests/integration/test_settings_ai.py`

**Acceptance:**
- [ ] GET `/settings/ai` render 3 slot + key form
- [ ] POST update slots → `users` UPDATE → publish `registry.invalidated`
- [ ] POST BYO key → Fernet encrypt → `users.api_keys_enc` UPDATE
- [ ] `/api/ai/test-key` POST → call provider with 1 token request → status

**Steps:**

- [ ] **Step 1: Route**

```python
# in src/web/routes/app.py
@router.get("/settings/ai")
async def settings_ai(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        boss = await c.fetchrow("SELECT * FROM users WHERE id=$1", ctx.boss_id)
        models = await c.fetch("SELECT * FROM models WHERE is_active=TRUE ORDER BY tier, name")
    return templates.TemplateResponse("settings_ai.html", _ctx(request, ctx) | {
        "boss": boss, "models": models,
    })

@router.post("/settings/ai")
async def save_ai(request: Request, ctx=Depends(get_current_boss)):
    verify_csrf(request)
    form = await request.form()
    smart = int(form.get("smart_model_id") or 0) or None
    fast = int(form.get("fast_model_id") or 0) or None
    vision = int(form.get("vision_model_id") or 0) or None
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        await c.execute("""UPDATE users SET smart_model_id=$2, fast_model_id=$3, vision_model_id=$4
                           WHERE id=$1""", ctx.boss_id, smart, fast, vision)
    return RedirectResponse("/settings/ai", status_code=303)

@router.post("/settings/ai/keys")
async def save_keys(request: Request, ctx=Depends(get_current_boss)):
    verify_csrf(request)
    form = await request.form()
    keys = {}
    for prov in ("openai","groq","gemini"):
        v = form.get(f"key_{prov}","").strip()
        if v: keys[prov] = v
    from cryptography.fernet import Fernet
    import json
    _f = Fernet(settings.FERNET_KEY.encode())
    blob = _f.encrypt(json.dumps(keys).encode())
    async with request.app.state.db_pool.acquire() as c:
        await c.execute("UPDATE users SET api_keys_enc=$2 WHERE id=$1", ctx.boss_id, blob)
    return RedirectResponse("/settings/ai", status_code=303)
```

- [ ] **Step 2: Template** — render từ §9.7 spec mockup. Quan trọng: vision slot show "Smart anh chọn (X) đã có vision — slot này có thể để trống" khi `smart_model.capabilities` chứa `vision`.

- [ ] **Step 3: Commit**

```bash
git add src/web/routes/app.py src/web/routes/api_ai.py src/web/templates/settings_ai.html tests/integration/test_settings_ai.py
git commit -m "feat(web): settings/ai — 3 slot model picker + BYO API keys"
```

---

## Batch H — Polish (security + observability)

Sau mọi batch trước.

### Task H1: Security hooks

**Depends on:** G1, G3, B2 (LLM call), E1 (channel)
**Files:**
- Create: `src/security/rate_limit.py` (RateLimiter Protocol + InMemoryRateLimiter)
- Create: `src/security/cost_cap.py` (LLM gateway pre-check daily cost vs cap)
- Modify: `src/web/routes/auth.py`, `routes/oauth.py`, `routes/admin.py`, `routes/api_ai.py` (apply rate limits)
- Modify: `src/llm/native.py` (cost cap check)
- Test: `tests/integration/test_security_hooks.py`

**Acceptance:**
- [ ] RateLimiter: `check(key, limit, window_sec) → bool`. Apply:
  - login `5/5min` per IP
  - oauth callback `30/min` per IP
  - LLM call `60/min` per boss
  - password reset `3/hour` per email
  - set_reminder `30/min` per boss
- [ ] Cost cap: `LLMGateway.complete` check `token_usage` 24h cost; nếu > `cost_cap_usd_daily` → degrade smart→fast hoặc reject
- [ ] PII redact processor đã enable trong observability (Task A2) — verify content fields redacted
- [ ] OAuth redirect whitelist strict match (đã enforce ở Task G1)

**Steps:**

- [ ] **Step 1: RateLimiter**

```python
# src/security/rate_limit.py
import time
from typing import Protocol
from collections import defaultdict

class RateLimiter(Protocol):
    async def check(self, key: str, limit: int, window_sec: int) -> bool: ...

class InMemoryRateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def check(self, key, limit, window_sec):
        now = time.time()
        bucket = self._hits[key]
        cutoff = now - window_sec
        # Drop old
        self._hits[key] = [t for t in bucket if t > cutoff]
        if len(self._hits[key]) >= limit:
            return False
        self._hits[key].append(now)
        return True
```

- [ ] **Step 2: Apply rate limit decorator pattern**

```python
# src/security/middleware.py
from fastapi import Request, HTTPException

async def rate_check(request: Request, key: str, limit: int, window_sec: int):
    limiter = request.app.state.rate_limiter
    if not await limiter.check(key, limit, window_sec):
        raise HTTPException(429, "rate limit")
```

Apply trong route:
```python
@router.post("/login")
async def login(request: Request, ...):
    ip = request.client.host
    await rate_check(request, f"login:{ip}", 5, 300)
    ...
```

- [ ] **Step 3: Cost cap**

```python
# src/security/cost_cap.py
async def check_cost_cap(pool, boss_id) -> tuple[bool, float, float]:
    """Returns (allowed, used_today, cap)."""
    async with pool.acquire() as c:
        used = await c.fetchval("""
          SELECT COALESCE(SUM(cost_usd), 0) FROM token_usage
          WHERE boss_id=$1 AND called_at > NOW() - INTERVAL '24 hours'
        """, boss_id)
        cap = await c.fetchval("SELECT cost_cap_usd_daily FROM users WHERE id=$1", boss_id)
    return float(used) < float(cap), float(used), float(cap)
```

```python
# src/llm/native.py — extend complete():
allowed, used, cap = await check_cost_cap(self.pool, req.boss_id)
if not allowed:
    # Degrade: force fast tier
    req.routing_hints["force_tier"] = "fast"
    # Or reject if even fast exceeds; for MVP: log warn + continue with fast
    log.warning("cost cap hit", extra={"boss_id": req.boss_id, "used": used, "cap": cap})
```

- [ ] **Step 4: Lifespan wire**

```python
# src/main.py
from src.security.rate_limit import InMemoryRateLimiter
# in lifespan:
app.state.rate_limiter = InMemoryRateLimiter()
```

- [ ] **Step 5: Commit**

```bash
git add src/security/ src/web/routes/*.py src/llm/native.py tests/integration/test_security_hooks.py src/main.py
git commit -m "feat(security): rate limiter + cost cap + apply hooks across routes"
```

---

### Task H2: Observability (Prometheus metrics + tracing propagation)

**Depends on:** B1 (EventBus), B2 (token_usage), D (trace_op context)
**Files:**
- Create: `src/infra/metrics.py` (Prometheus collectors)
- Modify: `src/main.py` (add `/metrics` route)
- Modify: subscribers to publish metrics on key events
- Modify: `src/llm/native.py`, `src/tools/dispatcher.py` (record latency + status histograms)
- Test: `tests/integration/test_metrics.py`

**Acceptance:**
- [ ] `/metrics` Prometheus format with:
  - `messages_ingested_total{provider,boss_id}`
  - `note_updates_total{boss_id,status}`
  - `llm_calls_total{provider,model,status,feature}`
  - `llm_call_latency_seconds{feature,tier}` histogram
  - `llm_cache_hit_ratio{feature,model}` gauge (rolling 1h)
  - `outbound_messages_total{channel,status}`
  - `retrieval_stage_latency_seconds{stage}` histogram
  - `tool_call_latency_seconds{tool}` histogram
- [ ] Trace context propagation: `trace_id`, `span_id` in structlog every log + `token_usage` + `tool_call_log` row

**Steps:**

- [ ] **Step 1: Metrics module**

```python
# src/infra/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

messages_ingested = Counter("messages_ingested_total", "Messages ingested", ["provider","boss_id"])
note_updates = Counter("note_updates_total", "Note rebuilds", ["boss_id","status"])
llm_calls = Counter("llm_calls_total", "LLM calls", ["provider","model","status","feature"])
llm_latency = Histogram("llm_call_latency_seconds", "LLM latency", ["feature","tier"])
outbound = Counter("outbound_messages_total", "Outbound messages", ["channel","status"])
retrieval_latency = Histogram("retrieval_stage_latency_seconds", "Retrieval stage latency", ["stage"])
tool_latency = Histogram("tool_call_latency_seconds", "Tool latency", ["tool"])
cache_hit_ratio = Gauge("llm_cache_hit_ratio", "Prompt cache hit ratio rolling 1h", ["feature","model"])
```

- [ ] **Step 2: Subscriber that records metrics**

```python
# src/infra/metrics_subscriber.py
def register(bus):
    async def on_message_captured(p):
        messages_ingested.labels(provider=p["provider"], boss_id=str(p["boss_id"])).inc()
    bus.subscribe("message.captured", on_message_captured)
    # ... other handlers
```

- [ ] **Step 3: /metrics route**

```python
# src/main.py
from fastapi.responses import Response
from src.infra.metrics import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4: Trace propagation**

`llm/native.py` `complete()` đã insert `token_usage` với `trace_id/span_id` từ `current().trace_id`. Tương tự `tool/dispatcher.py` `_invoke` insert `tool_call_log`.

Bind structlog context:
```python
# src/agents/context.py — trace_op extend:
@contextmanager
def trace_op(op_name, boss_id):
    tc = TraceCtx(...)
    structlog.contextvars.bind_contextvars(
        trace_id=tc.trace_id, span_id=tc.span_id, op=op_name, boss_id=boss_id)
    try: yield tc
    finally:
        structlog.contextvars.unbind_contextvars("trace_id","span_id","op","boss_id")
```

- [ ] **Step 5: Cache hit ratio gauge updater (cron)**

```python
# src/scheduler/jobs/cache_hit_ratio.py
async def job(app_state):
    async with app_state.db_pool.acquire() as c:
        rows = await c.fetch("""
          SELECT feature, model,
                 SUM(tokens_cached)::FLOAT / NULLIF(SUM(tokens_in),0) AS ratio
          FROM token_usage WHERE called_at > NOW() - INTERVAL '1 hour'
          GROUP BY feature, model
        """)
    for r in rows:
        cache_hit_ratio.labels(feature=r["feature"], model=r["model"]).set(r["ratio"] or 0)
```

- [ ] **Step 6: Commit**

```bash
git add src/infra/metrics.py src/infra/metrics_subscriber.py src/main.py src/scheduler/jobs/cache_hit_ratio.py
git commit -m "feat(observability): Prometheus /metrics + trace propagation + cache hit ratio"
```

---

## Task FINAL: End-to-end integration test

**Depends on:** all batches
**Files:**
- Create: `tests/e2e/test_full_flow.py`
- Create: `tests/e2e/fixtures/` (synthetic data: 1 boss, 1 bot acc platform, 1 group, 10 msg)

**Acceptance:**
- [ ] Flow 1 — Boss register: POST `/login` (email/pw) → user created → session cookie set
- [ ] Flow 2 — Admin assign bot acc: POST `/admin/bosses/:id/assign-zalo` → assignment pending → boss POST `/channels/accept` → linking_token generated
- [ ] Flow 3 — Boss link via DM: simulate inbound `/start <token>` to Node bridge (mock zca-js with fake events) → account_links INSERT → outbound ack
- [ ] Flow 4 — Capture: simulate inbound group message → message.captured event → row in `messages` + Qdrant point
- [ ] Flow 5 — Tag bot: simulate inbound `@bot tóm tắt nhóm` → InGroupResponder runs → outbound message logged (mock LLM)
- [ ] Flow 6 — Note update: 30 messages → threshold trigger → NoteUpdater fires → group_notes UPDATE → note.updated event
- [ ] Flow 7 — DM Q&A: boss DM bot → DMResponder fires → reply via outbound
- [ ] Flow 8 — Set reminder: agent tool `set_reminder` → row in `scheduled_reminders` → scheduler fires `reminder.due` → ReminderFirer sends → mark fired

**Steps:**

- [ ] **Step 1: Test harness**

```python
# tests/e2e/test_full_flow.py
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_full_flow(app, db_pool, monkeypatch):
    # Mock LLM
    async def fake_complete(req):
        if req.feature == "dm_general":
            return LLMResponse(content="OK em hiểu", tool_calls=[], status="ok",
                               usage=LLMUsage(50,10,0,200,"gpt-4o-mini","openai_compat"))
        if req.feature == "qa_with_search":
            return LLMResponse(content="Em tóm tắt: ...", tool_calls=[], status="ok",
                               usage=LLMUsage(200,50,0,500,"gpt-4o-mini","openai_compat"))
        return LLMResponse(content="(mock)", tool_calls=[], status="ok",
                          usage=LLMUsage(10,5,0,100,"x","x"))
    monkeypatch.setattr(app.state.llm_gateway, "complete", fake_complete)
    # Mock Zalo adapter — no real subprocess
    app.state.zalo.start_inbound = AsyncMock()
    sent_messages = []
    async def fake_send(bot_acc, chat_id, text, thread_kind):
        sent_messages.append({"chat_id": chat_id, "text": text, "thread_kind": thread_kind})
        return "ok"
    app.state.zalo.send_text = fake_send

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Flow 1: register
        r = await client.post("/api/register",
                              json={"email":"boss@test","password":"strongpass1234","name":"Đạt"})
        assert r.status_code == 200
        # ... continue with flows 2–8
```

- [ ] **Step 2: Commit**

```bash
git add tests/e2e/
git commit -m "test(e2e): full flow — register → link → capture → reply → reminder"
```

- [ ] **Step 3: Run full test suite**

```bash
docker compose up -d postgres qdrant
alembic upgrade head
pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected: ≥70% line coverage; ≥80% on `services/`, `agents/`.

---

## Cuối plan — Sanity checks

- [ ] Spec cover: mọi section 1–15 đã có task tương ứng (search lại spec)
- [ ] No `claude` / `anthropic` model in seed (verify với `grep -i claude config/seeds/`)
- [ ] `pgvector` không có ở `pyproject.toml` (verify với `grep pgvector pyproject.toml`)
- [ ] Self-review check (writing-plans skill):
  - [ ] Mọi task có files, acceptance, dependency, code blocks
  - [ ] Không có placeholder "TODO" / "fill in later"
  - [ ] Type consistency: signature match across tasks
  - [ ] Plan size: ~5200 dòng đầy đủ

---

## Execution handoff

Plan complete. Execute qua **subagent-driven-development**:
- Spike (Task 0) chạy trước, manual oversight vì cần user scan QR
- Sau spike GO: dispatch subagent task-by-task, fresh context per task
- Two-stage review giữa task: green tests + acceptance criteria check + commit verification
- Batch parallel (B1↔B2↔B3↔B4, D1↔D2↔D3↔D4, etc.) → có thể dispatch song song 2 subagent

**Risk gates:**
- Sau Task A5: pause + manual verify schema migration trên DB local
- Sau Task D1: smoke test end-to-end agent loop với 1 message thật (mock channel)
- Sau Task E1: real Zalo session test (live)
- Sau Task FINAL: full integration test pass trước khi ship

Plan saved: `docs/superpowers/plans/2026-05-31-smart-bot-mvp.md`.

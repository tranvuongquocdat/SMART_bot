# Media Reading + web_search + Superadmin Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot đọc được mọi link/media (web/báo, YouTube transcript, TikTok best-effort, PDF/DOCX/XLSX, ảnh) và tự tra web (`web_search`), với key/usage/chi phí quản lý ở superadmin (charts + báo lỗi key).

**Architecture:** Tái dùng lớp `src/media/` đã có (cắm dây + hoàn thiện adapters). Hai đường vào cùng gọi lớp này: on-demand (`fetch_url`/`web_search` tools) + đính kèm inbound (điền `media_text`). `web_search` qua provider pluggable (Tavily/httpx); key+cost ở bảng `platform_integrations`+`integration_usage`, hiển thị trên trang superadmin.

**Tech Stack:** Python/FastAPI/asyncpg, pytest; trafilatura, yt-dlp, youtube-transcript-api, pypdf/python-docx/openpyxl, pillow(-heif); React/TS (Vite SPA) + charts.tsx; Tavily REST via httpx; Fernet (cryptography).

**Spec:** `docs/superpowers/specs/2026-06-19-doc-media-web-search-design.md`

**Conventions (đọc trước khi bắt đầu):**
- `ToolContext` (`src/tools/base.py`) expose: `boss_id`, `boss_role`, `pool`, `qdrant`, `bus`, `memory`, `llm` (LLMGateway). Tool nhận `ctx` đầu tiên.
- Media layer: `src/media/registry.py` (`find_adapter(media_kind=None, url=None, **kwargs)`, `_detect_from_url` → youtube/tiktok/url), `src/media/adapters/{web,document,image}.py`. `adapters/__init__.py` HIỆN RỖNG (bug gốc). ImageExtractor `__init__(llm_gateway, pool, boss_id)`, `requires_caps={"vision"}`.
- Fernet sẵn ở `src/llm/api_keys.py` (`_fernet`).
- Tool đăng ký: `@tool(...)` ở `src/tools/core/` + thêm tên vào `tools={...}` của `src/agents/dm_responder.py` và `src/agents/in_group_responder.py`.
- Prompt: sửa `config/seeds/prompts/*.yaml` (bump `version`) → `uv run python scripts/seed_prompts.py`.
- DB local: `postgresql://smart:smart@localhost:5433/smart_bot`. Migrations: alembic (`uv run alembic upgrade head`; revision mới trong `migrations/versions/`).
- Test channel: `ENABLE_WEB_TEST_CHANNEL=true`; harness `scripts/harness.py`.
- **Commit:** KHÔNG thêm Claude co-author (quy ước repo). Nhánh hiện tại: `feat/media-web-search`.

---

## PHASE 1 — Cắm dây media layer + `fetch_url` đọc được web/báo (đường A, gỡ nỗi đau chính)

### Task 1: Wire-up adapters (register tại import)

**Files:**
- Modify: `src/media/adapters/__init__.py` (đang rỗng)
- Test: `tests/unit/test_media_registry.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_media_registry.py
import src.media.adapters  # noqa: F401  (kích hoạt self-register)
from src.media.registry import find_adapter, list_adapters


def test_adapters_registered():
    kinds = set().union(*(a.supports for a in list_adapters()))
    assert {"url", "youtube", "tiktok", "pdf", "docx", "xlsx", "txt", "image"} <= kinds


def test_find_adapter_for_url():
    a = find_adapter(url="https://example.com/article")
    assert a.__class__.__name__ == "WebExtractor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_media_registry.py -v`
Expected: FAIL (`list_adapters()` empty → assertion fails / `find_adapter` raises `LookupError: no adapter`).

- [ ] **Step 3: Implement — import adapters in package init**

```python
# src/media/adapters/__init__.py
"""Import adapters so their @media_adapter decorators self-register."""

from src.media.adapters import document, image, web  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_media_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/media/adapters/__init__.py tests/unit/test_media_registry.py
git commit -m "fix(media): wire adapters so they self-register"
```

### Task 2: `fetch_url` viết lại — detect kind, fetch bytes, route adapter

**Files:**
- Modify: `src/tools/core/web.py` (thay thân `fetch_url`)
- Test: `tests/unit/test_fetch_url.py` (create)

Helper hợp đồng: `fetch_url(ctx, url)` trả `ToolResult(content={"title","text"})` hoặc `ToolResult(content=None, error=...)`. Document/image cần bytes → tự GET; web/youtube/tiktok → adapter tự xử. Cap text = `MAX_BODY_BYTES` (50KB) — import từ `src.media.adapters.web`.

- [ ] **Step 1: Write the failing test** (mock adapter + httpx)

```python
# tests/unit/test_fetch_url.py
import types
import pytest
from src.tools.core import web as web_tool


class _FakeCtx:
    def __init__(self):
        self.boss_id = 1
        self.boss_role = "boss"
        self.pool = None
        self.llm = None


@pytest.mark.asyncio
async def test_fetch_url_generic_uses_adapter(monkeypatch):
    from src.media.base import MediaExtractResult

    class _FakeWeb:
        async def extract(self, url=None, content=None, content_type=None):
            return MediaExtractResult(media_text="hello body", title="T")

    monkeypatch.setattr(web_tool, "find_adapter", lambda **kw: _FakeWeb())
    res = await web_tool.fetch_url(_FakeCtx(), "https://example.com/a")
    assert res.error is None
    assert res.content["title"] == "T"
    assert "hello body" in res.content["text"]


@pytest.mark.asyncio
async def test_fetch_url_reports_error(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(web_tool, "find_adapter", _boom)
    res = await web_tool.fetch_url(_FakeCtx(), "https://x.test")
    assert res.content is None
    assert res.error and "boom" in res.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_fetch_url.py -v`
Expected: FAIL (current `fetch_url` doesn't import `find_adapter` at module scope / shape differs).

- [ ] **Step 3: Implement the rewrite**

```python
# src/tools/core/web.py  (replace whole file)
"""Web tool — fetch_url: route any URL through the media layer."""

from __future__ import annotations

import httpx

import src.media.adapters  # noqa: F401  (self-register adapters)
from src.media.adapters.web import MAX_BODY_BYTES
from src.media.registry import find_adapter
from src.tools.base import ToolResult
from src.tools.registry import tool

_DOC_EXT = ("pdf", "docx", "xlsx", "txt")
_DOC_CT = ("application/pdf", "wordprocessingml", "msword",
           "spreadsheetml", "ms-excel", "text/")


def _needs_bytes(url: str, content_type: str) -> str | None:
    """Return media_kind ('pdf'/'docx'/'xlsx'/'txt'/'image') if this URL is a
    document/image that the adapter needs raw bytes for; else None."""
    u = url.lower().split("?", 1)[0]
    ct = (content_type or "").lower()
    if ct.startswith("image/") or u.rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp", "heic", "gif"):
        return "image"
    for ext in _DOC_EXT:
        if u.endswith("." + ext):
            return ext
    if "pdf" in ct:
        return "pdf"
    if "wordprocessingml" in ct or "msword" in ct:
        return "docx"
    if "spreadsheetml" in ct or "ms-excel" in ct:
        return "xlsx"
    if ct.startswith("text/plain"):
        return "txt"
    return None


@tool(
    name="fetch_url",
    description="Đọc nội dung 1 URL → text + title. Hỗ trợ web/báo, YouTube (transcript), "
                "TikTok (best-effort), PDF/DOCX/XLSX, ảnh. Dùng khi user đưa link hoặc cần đọc nội dung link.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    feature="url_summarize",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=40,
)
async def fetch_url(ctx, url: str) -> ToolResult:
    try:
        # Probe content-type cheaply; many doc/image URLs have no extension.
        content_type = ""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as c:
                head = await c.head(url)
                content_type = head.headers.get("content-type", "")
        except Exception:
            content_type = ""

        kind = _needs_bytes(url, content_type)
        if kind in ("pdf", "docx", "xlsx", "txt"):
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
                r = await c.get(url)
                r.raise_for_status()
            adapter = find_adapter(media_kind=kind)
            result = await adapter.extract(content=r.content, content_type=content_type or None, url=url)
        elif kind == "image":
            adapter = find_adapter(media_kind="image", llm_gateway=ctx.llm,
                                   pool=ctx.pool, boss_id=ctx.boss_id)
            result = await adapter.extract(url=url)  # ImageExtractor fetches bytes itself
        else:
            adapter = find_adapter(url=url)  # url / youtube / tiktok
            result = await adapter.extract(url=url)

        text = (result.media_text or "")[:MAX_BODY_BYTES]
        if not text.strip():
            return ToolResult(content=None, error="empty_content: không trích được nội dung từ link")
        return ToolResult(content={"title": result.title or "", "text": text})
    except httpx.HTTPStatusError as e:
        return ToolResult(content=None, error=f"http_{e.response.status_code}: không tải được link")
    except Exception as e:  # noqa: BLE001
        return ToolResult(content=None, error=f"fetch_failed: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_fetch_url.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/tools/core/web.py tests/unit/test_fetch_url.py
git commit -m "feat(media): fetch_url routes URLs through the media layer"
```

### Task 3: Verify đọc web thật qua bot (harness, đường A)

**Files:** none (verification only).

- [ ] **Step 1:** Khởi động server có test channel: `bash scripts/restart.sh` (hoặc `ENABLE_WEB_TEST_CHANNEL=true uv run uvicorn src.main:app --port 8000`). Seed nếu cần: `bash scripts/seed_llm.sh && uv run python scripts/seed_prompts.py`. Setup harness nếu chưa: `uv run python scripts/harness.py setup`.
- [ ] **Step 2:** Hỏi bot kèm link báo: `uv run python scripts/harness.py ask "Tóm tắt giúp anh bài này: https://vnexpress.net/ (chọn 1 URL bài cụ thể)"`. Expected: bot gọi `fetch_url`, trả tóm tắt ĐÚNG nội dung (không nói "không đọc được link").
- [ ] **Step 3:** Regression: `uv run python scripts/harness.py gold` → vẫn 11/11. (Phase 1 KHÔNG đụng prompt/extract → kỳ vọng xanh.)
- [ ] **Step 4: Commit** (nếu có chỉnh) — nếu không, không cần.

---

## PHASE 2 — YouTube transcript thật + TikTok best-effort + ảnh qua fetch_url

### Task 4: Thêm dep `youtube-transcript-api`

**Files:** Modify `pyproject.toml`

- [ ] **Step 1:** Thêm `"youtube-transcript-api>=1.0",` vào mảng `dependencies` trong `pyproject.toml` (cạnh `yt-dlp`).
- [ ] **Step 2:** `uv sync` → đảm bảo cài thành công.
- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add youtube-transcript-api"
```

### Task 5: YouTube transcript thật trong WebExtractor

**Files:**
- Modify: `src/media/adapters/web.py` (`_youtube`, `_pick_subtitle` → fetch transcript thật)
- Test: `tests/unit/test_web_extractor.py` (create)

- [ ] **Step 1: Write the failing test** (mock youtube_transcript_api)

```python
# tests/unit/test_web_extractor.py
import pytest
from src.media.adapters.web import WebExtractor


@pytest.mark.asyncio
async def test_youtube_uses_transcript(monkeypatch):
    import src.media.adapters.web as web

    class _FakeAPI:
        @staticmethod
        def get_transcript(video_id, languages=None):
            return [{"text": "xin chào"}, {"text": "phần hai"}]

    monkeypatch.setattr(web, "_yt_transcript", lambda vid: "xin chào phần hai")
    monkeypatch.setattr(web, "_yt_meta", lambda url: ("Tiêu đề video", "vid123", "desc"))
    res = await WebExtractor().extract(url="https://youtu.be/vid123")
    assert "xin chào phần hai" in res.media_text
    assert res.title == "Tiêu đề video"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_web_extractor.py -v`
Expected: FAIL (`_yt_transcript`/`_yt_meta` chưa tồn tại).

- [ ] **Step 3: Implement** — tách helper, lấy transcript thật, fallback description

```python
# src/media/adapters/web.py — thay _youtube + _pick_subtitle bằng:

def _yt_video_id(url: str) -> str | None:
    import re
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _yt_transcript(video_id: str) -> str:
    """Transcript thật (vi→en, cả auto-sub). Rỗng nếu không có / bị chặn."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=["vi", "en"])
        return " ".join(s["text"] for s in segs if s.get("text")).strip()
    except Exception:
        log.info("yt transcript unavailable/blocked vid=%s", video_id)
        return ""


def _yt_meta(url: str) -> tuple[str, str | None, str]:
    """(title, video_id, description) qua yt-dlp; degrade rỗng nếu lỗi."""
    try:
        import yt_dlp  # type: ignore
        with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return (info.get("title") or "", info.get("id"), info.get("description") or "")
    except Exception:
        log.exception("yt-dlp meta failed url=%s", url)
        return ("", _yt_video_id(url), "")
```

Và `_youtube` trở thành:

```python
    async def _youtube(self, url: str) -> MediaExtractResult:
        title, vid, desc = _yt_meta(url)
        vid = vid or _yt_video_id(url)
        transcript = _yt_transcript(vid) if vid else ""
        body = transcript or desc  # transcript ưu tiên, fallback description
        text = (f"{title}\n\n{body}").strip()
        if len(text.encode("utf-8")) > MAX_BODY_BYTES:
            text = text.encode("utf-8")[:MAX_BODY_BYTES].decode("utf-8", errors="ignore")
        return MediaExtractResult(media_text=text, title=title or None, extra={"video_id": vid})
```

(Xoá hàm `_pick_subtitle` cũ; bỏ import yt_dlp ở đầu nếu chỉ dùng trong helper.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_web_extractor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/media/adapters/web.py tests/unit/test_web_extractor.py
git commit -m "feat(media): real YouTube transcript via youtube-transcript-api"
```

### Task 6: TikTok best-effort (metadata, không generic trafilatura)

**Files:**
- Modify: `src/media/adapters/web.py` (`extract` route tiktok riêng + `_tiktok`)
- Test: `tests/unit/test_web_extractor.py` (thêm case)

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_tiktok_best_effort(monkeypatch):
    import src.media.adapters.web as web
    monkeypatch.setattr(web, "_yt_meta", lambda url: ("TT title", "ttid", "mô tả tiktok"))
    res = await web.WebExtractor().extract(url="https://www.tiktok.com/@x/video/123")
    assert "mô tả tiktok" in res.media_text
    assert res.title == "TT title"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_web_extractor.py::test_tiktok_best_effort -v`
Expected: FAIL (tiktok hiện rơi vào `_generic`).

- [ ] **Step 3: Implement** — route tiktok + `_tiktok` (yt-dlp metadata; transcript đầy đủ = ASR phase sau)

```python
    async def extract(self, url=None, content=None, content_type=None):
        if not url:
            return MediaExtractResult(media_text="")
        if "youtube.com" in url or "youtu.be" in url:
            return await self._youtube(url)
        if "tiktok.com" in url:
            return await self._tiktok(url)
        return await self._generic(url)

    async def _tiktok(self, url: str) -> MediaExtractResult:
        # Best-effort: title + description + subtitle-nếu-có (yt-dlp). Transcript
        # đầy đủ cần ASR (phase sau). Không dùng trafilatura trên HTML tiktok.
        title, _vid, desc = _yt_meta(url)
        text = (f"{title}\n\n{desc}").strip()
        return MediaExtractResult(media_text=text, title=title or None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_web_extractor.py -v`
Expected: PASS (cả 2 case).

- [ ] **Step 5: Commit**

```bash
git add src/media/adapters/web.py tests/unit/test_web_extractor.py
git commit -m "feat(media): TikTok best-effort metadata extraction"
```

### Task 7: Unit test document + image adapter (đường bytes qua fetch_url)

**Files:** Test `tests/unit/test_document_extractor.py` (create)

- [ ] **Step 1: Write the failing test** (PDF tối giản tạo bằng pypdf/ reportlab-free — dùng pypdf writer)

```python
# tests/unit/test_document_extractor.py
import io
import pytest
from src.media.adapters.document import DocumentExtractor


@pytest.mark.asyncio
async def test_txt_extract():
    res = await DocumentExtractor().extract(content=b"hello\tworld", content_type="text/plain")
    assert "hello" in res.media_text


@pytest.mark.asyncio
async def test_unknown_kind_empty():
    res = await DocumentExtractor().extract(content=b"x", content_type="application/zip")
    assert res.media_text == ""
```

- [ ] **Step 2: Run test to verify it fails/passes**

Run: `uv run pytest tests/unit/test_document_extractor.py -v`
Expected: PASS (DocumentExtractor đã có; test chốt hợp đồng). Nếu FAIL → sửa adapter.

- [ ] **Step 3: (nếu PASS) Commit**

```bash
git add tests/unit/test_document_extractor.py
git commit -m "test(media): document extractor txt + unknown-kind"
```

- [ ] **Step 4: Verify ảnh-qua-URL thủ công** (cần vision model cấu hình cho boss harness): `uv run python scripts/harness.py ask "Đọc giúp anh ảnh này: <image_url công khai .jpg>"`. Expected: bot mô tả/OCR ảnh. Nếu boss chưa có vision model → trả rỗng (degrade, không crash) — ghi nhận để cấu hình vision model ở Phase 4 nếu cần.

---

## PHASE 3 — `web_search` tool + TavilyProvider (key tạm .env để chạy)

### Task 8: SearchProvider interface + TavilyProvider (httpx)

**Files:**
- Create: `src/search/__init__.py`, `src/search/base.py`, `src/search/tavily.py`
- Test: `tests/unit/test_tavily_provider.py`

- [ ] **Step 1: Write the failing test** (mock httpx response)

```python
# tests/unit/test_tavily_provider.py
import pytest
import httpx
from src.search.tavily import TavilyProvider


@pytest.mark.asyncio
async def test_tavily_parses_results(monkeypatch):
    payload = {"results": [{"title": "T", "url": "https://u", "content": "body", "score": 0.9}]}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return payload

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    res = await TavilyProvider(api_key="k").search("hello", max_results=3)
    assert res[0].title == "T" and res[0].url == "https://u" and "body" in res[0].content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tavily_provider.py -v`
Expected: FAIL (module chưa có).

- [ ] **Step 3: Implement**

```python
# src/search/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    content: str = ""


class SearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...
```

```python
# src/search/tavily.py
from __future__ import annotations
import httpx
from src.search.base import SearchResult

_ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        body = {"api_key": self.api_key, "query": query,
                "max_results": max_results, "include_answer": False}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(_ENDPOINT, json=body)
            r.raise_for_status()
            data = r.json()
        out = []
        for it in data.get("results", []):
            out.append(SearchResult(
                title=it.get("title") or "", url=it.get("url") or "",
                snippet=(it.get("content") or "")[:300], content=it.get("content") or ""))
        return out
```

```python
# src/search/__init__.py
"""Pluggable web-search providers."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_tavily_provider.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/search/ tests/unit/test_tavily_provider.py
git commit -m "feat(search): Tavily provider behind SearchProvider interface"
```

### Task 9: `web_search` tool (key tạm từ settings)

**Files:**
- Create: `src/tools/core/search_web.py`
- Modify: `src/config.py` (thêm `TAVILY_API_KEY` env tạm — Phase 4 chuyển sang DB), `src/agents/dm_responder.py`, `src/agents/in_group_responder.py` (thêm `"web_search"` vào `tools={...}`)
- Test: `tests/unit/test_web_search_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_web_search_tool.py
import pytest
from src.tools.core import search_web
from src.search.base import SearchResult


class _Ctx:
    boss_id = 1; boss_role = "boss"; pool = None; llm = None


@pytest.mark.asyncio
async def test_web_search_returns_results(monkeypatch):
    async def _fake_provider(ctx):
        class P:
            async def search(self, q, *, max_results=5):
                return [SearchResult(title="A", url="https://a", snippet="s", content="c")]
        return P()
    monkeypatch.setattr(search_web, "_get_provider", _fake_provider)
    res = await search_web.web_search(_Ctx(), "tin tức")
    assert res.error is None and res.content[0]["url"] == "https://a"


@pytest.mark.asyncio
async def test_web_search_no_key(monkeypatch):
    async def _none(ctx): return None
    monkeypatch.setattr(search_web, "_get_provider", _none)
    res = await search_web.web_search(_Ctx(), "x")
    assert res.content is None and "cấu hình" in (res.error or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_web_search_tool.py -v`
Expected: FAIL (module chưa có).

- [ ] **Step 3: Implement tool + provider resolver (key từ settings tạm)**

```python
# src/tools/core/search_web.py
from __future__ import annotations
from src.config import settings
from src.tools.base import ToolResult
from src.tools.registry import tool


async def _get_provider(ctx):
    """Phase 3: key từ settings.TAVILY_API_KEY. Phase 4: đọc từ platform_integrations."""
    key = getattr(settings, "TAVILY_API_KEY", "") or ""
    if not key:
        return None
    from src.search.tavily import TavilyProvider
    return TavilyProvider(api_key=key)


@tool(
    name="web_search",
    description="Tra cứu web (tin tức/thông tin ngoài kho tri thức). Trả danh sách {title,url,snippet}. "
                "Sau khi search, dùng fetch_url để đọc sâu 1 kết quả nếu cần.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    feature="web_search",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=25,
)
async def web_search(ctx, query: str, max_results: int = 5) -> ToolResult:
    provider = await _get_provider(ctx)
    if provider is None:
        return ToolResult(content=None, error="search_unconfigured: chưa cấu hình tìm kiếm web")
    try:
        results = await provider.search(query, max_results=max_results)
    except Exception as e:  # noqa: BLE001
        return ToolResult(content=None, error=f"search_failed: {e}")
    return ToolResult(content=[{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results])
```

`src/config.py`: thêm field `TAVILY_API_KEY: str = Field("", validation_alias=AliasChoices("TAVILY_API_KEY"))` (theo mẫu các key khác trong file).

`src/agents/dm_responder.py` và `src/agents/in_group_responder.py`: thêm `"web_search"` vào set `tools={...}` (cạnh `"fetch_url"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_web_search_tool.py -v`
Expected: PASS (2 case).

- [ ] **Step 5: Commit**

```bash
git add src/tools/core/search_web.py src/config.py src/agents/dm_responder.py src/agents/in_group_responder.py tests/unit/test_web_search_tool.py
git commit -m "feat(search): web_search tool (key from settings, temporary)"
```

---

## PHASE 4 — Integration superadmin: bảng key + cost + health + endpoints + charts

### Task 10: Migration `platform_integrations` + `integration_usage`

**Files:** Create `migrations/versions/00NN_platform_integrations.py` (NN = số kế tiếp — xem `migrations/versions/` để lấy revision mới nhất; KHÔNG đụng 0014 WIP của AI-settings — đặt revision sau head hiện tại).

- [ ] **Step 1:** Xác định head: `uv run alembic heads`. Tạo file revision mới với `down_revision = <head>`.
- [ ] **Step 2: Implement migration**

```python
# migrations/versions/00NN_platform_integrations.py
from alembic import op

revision = "00NN_platform_integrations"
down_revision = "<HEAD>"  # điền head thực tế
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE platform_integrations (
          provider       TEXT PRIMARY KEY,
          api_key_enc    TEXT,
          unit_cost_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
          status         JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE integration_usage (
          provider   TEXT NOT NULL,
          boss_id    INTEGER NOT NULL,
          day        DATE NOT NULL,
          count      INTEGER NOT NULL DEFAULT 0,
          cost_usd   NUMERIC(12,6) NOT NULL DEFAULT 0,
          PRIMARY KEY (provider, boss_id, day)
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS integration_usage")
    op.execute("DROP TABLE IF EXISTS platform_integrations")
```

- [ ] **Step 3:** `uv run alembic upgrade head` → verify 2 bảng: `psql ... -c "\d platform_integrations"`.
- [ ] **Step 4: Commit**

```bash
git add migrations/versions/00NN_platform_integrations.py
git commit -m "feat(db): platform_integrations + integration_usage tables"
```

### Task 11: Repo `PlatformIntegrationsRepo` (get/set key + cost, usage rollup)

**Files:**
- Create: `src/repositories/platform_integrations.py`
- Test: `tests/integration/test_platform_integrations_repo.py` (dùng DB local)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_platform_integrations_repo.py
import pytest, asyncpg
from src.repositories.platform_integrations import PlatformIntegrationsRepo

DSN = "postgresql://smart:smart@localhost:5433/smart_bot"


@pytest.mark.asyncio
async def test_set_get_key_and_usage():
    pool = await asyncpg.create_pool(DSN)
    repo = PlatformIntegrationsRepo(pool)
    await repo.set_config("tavily", api_key="secret123", unit_cost_usd=0.008)
    cfg = await repo.get("tavily")
    assert cfg["unit_cost_usd"] == 0.008
    assert await repo.get_api_key("tavily") == "secret123"   # decrypted
    await repo.record_usage("tavily", boss_id=1, cost_usd=0.008)
    await repo.record_usage("tavily", boss_id=1, cost_usd=0.008)
    usage = await repo.usage_totals("tavily")
    assert usage["count"] == 2
    await pool.execute("DELETE FROM integration_usage WHERE provider='tavily'")
    await pool.execute("DELETE FROM platform_integrations WHERE provider='tavily'")
    await pool.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_platform_integrations_repo.py -v`
Expected: FAIL (repo chưa có).

- [ ] **Step 3: Implement** (mã hoá Fernet tái dùng `src/llm/api_keys.py::_fernet`)

```python
# src/repositories/platform_integrations.py
from __future__ import annotations
import datetime as dt
from src.llm.api_keys import _fernet


class PlatformIntegrationsRepo:
    def __init__(self, pool):
        self.pool = pool

    async def set_config(self, provider, *, api_key=None, unit_cost_usd=None):
        enc = _fernet.encrypt(api_key.encode()).decode() if api_key else None
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO platform_integrations(provider, api_key_enc, unit_cost_usd, updated_at)
                VALUES($1, COALESCE($2, NULL), COALESCE($3, 0), now())
                ON CONFLICT (provider) DO UPDATE SET
                  api_key_enc = COALESCE($2, platform_integrations.api_key_enc),
                  unit_cost_usd = COALESCE($3, platform_integrations.unit_cost_usd),
                  updated_at = now()
            """, provider, enc, unit_cost_usd)

    async def get(self, provider) -> dict | None:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT provider, unit_cost_usd, status, "
                                 "(api_key_enc IS NOT NULL) AS has_key, updated_at "
                                 "FROM platform_integrations WHERE provider=$1", provider)
        return dict(r) | {"unit_cost_usd": float(r["unit_cost_usd"])} if r else None

    async def get_api_key(self, provider) -> str | None:
        async with self.pool.acquire() as c:
            enc = await c.fetchval("SELECT api_key_enc FROM platform_integrations WHERE provider=$1", provider)
        return _fernet.decrypt(enc.encode()).decode() if enc else None

    async def set_status(self, provider, ok: bool, message: str):
        import json
        status = json.dumps({"ok": ok, "message": message,
                             "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        async with self.pool.acquire() as c:
            await c.execute("UPDATE platform_integrations SET status=$2::jsonb WHERE provider=$1",
                            provider, status)

    async def record_usage(self, provider, *, boss_id: int, cost_usd: float):
        today = dt.date.today()
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO integration_usage(provider, boss_id, day, count, cost_usd)
                VALUES($1,$2,$3,1,$4)
                ON CONFLICT (provider, boss_id, day) DO UPDATE SET
                  count = integration_usage.count + 1,
                  cost_usd = integration_usage.cost_usd + $4
            """, provider, boss_id, today, cost_usd)

    async def usage_totals(self, provider) -> dict:
        async with self.pool.acquire() as c:
            r = await c.fetchrow("SELECT COALESCE(SUM(count),0) AS count, "
                                 "COALESCE(SUM(cost_usd),0) AS cost FROM integration_usage WHERE provider=$1", provider)
        return {"count": int(r["count"]), "cost": float(r["cost"])}

    async def usage_daily(self, provider, days: int = 30) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("""
                SELECT day, SUM(count) AS count, SUM(cost_usd) AS cost
                FROM integration_usage WHERE provider=$1 AND day >= current_date - $2::int
                GROUP BY day ORDER BY day DESC""", provider, days)
        return [{"date": r["day"].isoformat(), "count": int(r["count"]), "cost_usd": float(r["cost"])} for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_platform_integrations_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/platform_integrations.py tests/integration/test_platform_integrations_repo.py
git commit -m "feat(integrations): PlatformIntegrationsRepo (key + cost + usage)"
```

### Task 12: Superadmin endpoints (get/set/test/usage)

**Files:**
- Modify: `src/web/routes/api_superadmin.py` (thêm 4 route dưới `require_superadmin`)
- Test: `tests/integration/test_api_integrations.py`

- [ ] **Step 1: Write the failing test** (mock Tavily trong test endpoint, dùng session superadmin — theo mẫu test có sẵn trong `tests/integration/`)

```python
# tests/integration/test_api_integrations.py  (skeleton — theo mẫu test API hiện có để mint session superadmin)
# GET /api/v1/superadmin/integrations → 200, list có 'tavily'
# PUT .../integrations/tavily {api_key, unit_cost_usd} → 200; GET phản ánh has_key=true, unit_cost
# POST .../integrations/tavily/test (monkeypatch provider) → status.ok cập nhật
# GET .../integrations/tavily/usage?range=30 → {totals, daily}
```

(Đọc 1 test API superadmin sẵn có trong `tests/integration/` để copy cách tạo client + session trước khi viết.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_api_integrations.py -v`
Expected: FAIL (routes chưa có).

- [ ] **Step 3: Implement endpoints**

```python
# Thêm vào src/web/routes/api_superadmin.py
from src.repositories.platform_integrations import PlatformIntegrationsRepo

@router.get("/integrations")
async def list_integrations(db=Depends(get_db), _: BossContext = Depends(require_superadmin)):
    repo = PlatformIntegrationsRepo(db)
    cfg = await repo.get("tavily") or {"provider": "tavily", "unit_cost_usd": 0, "has_key": False, "status": {}}
    return [{**cfg, **(await repo.usage_totals("tavily"))}]

@router.put("/integrations/{provider}", dependencies=[Depends(verify_json_csrf)])
async def set_integration(provider: str, payload: dict, db=Depends(get_db), _: BossContext = Depends(require_superadmin)):
    repo = PlatformIntegrationsRepo(db)
    await repo.set_config(provider, api_key=payload.get("api_key") or None,
                          unit_cost_usd=payload.get("unit_cost_usd"))
    return {"ok": True}

@router.post("/integrations/{provider}/test", dependencies=[Depends(verify_json_csrf)])
async def test_integration(provider: str, db=Depends(get_db), _: BossContext = Depends(require_superadmin)):
    repo = PlatformIntegrationsRepo(db)
    key = await repo.get_api_key(provider)
    if not key:
        await repo.set_status(provider, False, "Chưa có key")
        return {"ok": False, "message": "Chưa có key"}
    from src.search.tavily import TavilyProvider
    try:
        await TavilyProvider(api_key=key).search("ping", max_results=1)
        await repo.set_status(provider, True, "OK")
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        await repo.set_status(provider, False, str(e)[:200])
        return {"ok": False, "message": str(e)[:200]}

@router.get("/integrations/{provider}/usage")
async def integration_usage(provider: str, range: int = 30, db=Depends(get_db), _: BossContext = Depends(require_superadmin)):
    repo = PlatformIntegrationsRepo(db)
    return {"totals": await repo.usage_totals(provider), "daily": await repo.usage_daily(provider, range)}
```

(Kiểm import `Depends`, `get_db`, `require_superadmin`, `BossContext`, `verify_json_csrf` đã có ở đầu file; thêm nếu thiếu.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_api_integrations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/api_superadmin.py tests/integration/test_api_integrations.py
git commit -m "feat(integrations): superadmin endpoints (config/test/usage)"
```

### Task 13: web_search đọc key từ DB + ghi usage/cost + cập nhật status khi lỗi

**Files:**
- Modify: `src/tools/core/search_web.py` (`_get_provider` đọc DB; sau search ghi usage; lỗi key → set_status)
- Test: `tests/unit/test_web_search_tool.py` (cập nhật để mock repo)

- [ ] **Step 1: Update test** — `_get_provider` lấy từ repo; thêm case ghi usage gọi `record_usage`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement**

```python
# search_web.py — thay _get_provider + thêm ghi usage trong web_search
async def _get_provider(ctx):
    from src.repositories.platform_integrations import PlatformIntegrationsRepo
    repo = PlatformIntegrationsRepo(ctx.pool)
    key = await repo.get_api_key("tavily")
    if not key:
        return None
    from src.search.tavily import TavilyProvider
    return TavilyProvider(api_key=key)

# trong web_search(): sau khi search OK →
#   cfg = await PlatformIntegrationsRepo(ctx.pool).get("tavily")
#   await PlatformIntegrationsRepo(ctx.pool).record_usage("tavily", boss_id=ctx.boss_id, cost_usd=float(cfg["unit_cost_usd"]))
# nếu search raise lỗi 401/quota → set_status("tavily", False, str(e)) trước khi trả error
```

- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit**

```bash
git add src/tools/core/search_web.py tests/unit/test_web_search_tool.py
git commit -m "feat(search): web_search uses DB key + records usage/cost"
```

### Task 14: FE — trang/section Integrations superadmin (key + status + cost charts)

**Files:**
- Create: `frontend/src/modules/superadmin/features/integrations/{api.ts,page.tsx}`
- Modify: `frontend/src/modules/superadmin/nav.ts` (+route), router superadmin, `frontend/src/locales/{vi,en}.ts`

Theo mẫu `frontend/src/modules/admin/features/usage/page.tsx` (card tổng + `BarChart` cost theo ngày từ `@/components/charts`) + mẫu Select/Input/Button. Query qua `@/lib/api`.

- [ ] **Step 1:** `api.ts` — `integrationsQuery()` (GET list), `usageQuery(provider, range)` (GET usage), `setIntegration(provider, payload)` (PUT), `testIntegration(provider)` (POST).
- [ ] **Step 2:** `page.tsx` — section: input API key + input `unit_cost_usd` + nút "Lưu" (PUT) + nút "Kiểm tra" (POST → toast + badge status xanh/đỏ + message + checked_at). Card: số query · tổng chi phí · trạng thái key. `BarChart` chi phí theo ngày (map `usage.daily` → `{label: dm(date), value: cost_usd}`). i18n `integrations.*`.
- [ ] **Step 3:** Đăng ký nav + route superadmin (theo mẫu các feature superadmin khác). i18n vi/en parity.
- [ ] **Step 4:** Build: `cd frontend && npm run build` → sạch (typecheck/lint).
- [ ] **Step 5:** Chụp UI xác nhận (Playwright/chromium, cookie superadmin qua `make_session` — xem mẫu P1): trang render, nhập key giả → Kiểm tra → badge đỏ (key sai) đúng; chart rỗng/zero hiển thị ổn, dark-mode không viền trắng.
- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/superadmin/features/integrations/ frontend/src/modules/superadmin/nav.ts frontend/src/locales/vi.ts frontend/src/locales/en.ts
git commit -m "feat(integrations): superadmin Integrations page (key/status/cost charts)"
```

---

## PHASE 5 — Đường B (đính kèm inbound) + prompt responder

### Task 15: Media enrichment cho tin có media_url (đường B)

**Files:**
- Create: `src/services/media_enrichment.py` (subscriber `message.captured` → nếu `media_url` → media layer → cập nhật `media_text`)
- Modify: nơi đăng ký subscribers (xem `src/main.py` / nơi `InboundIngest.register()` được gọi) để wire service
- Test: `tests/integration/test_media_enrichment.py`

- [ ] **Step 1: Write the failing test** — insert message có media_url (image/pdf giả, monkeypatch find_adapter trả MediaExtractResult), chạy enrichment handler, assert `media_text` được điền.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — handler async: nhận `{message_id, boss_id, ...}`; load message; nếu `media_url` & `media_text` rỗng → `find_adapter(media_kind=<từ media_kind/url>, llm_gateway=..., pool=..., boss_id=...)` → `extract` → `UPDATE messages SET media_text=$1`. Cache qua media_cache (ImageExtractor đã tự cache). Off hot-path (subscribe, không block ingest).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit**

```bash
git add src/services/media_enrichment.py src/main.py tests/integration/test_media_enrichment.py
git commit -m "feat(media): enrich inbound attachments into media_text"
```

### Task 16: Prompt responder — chủ động đọc link/tra web, không từ chối, ngắn gọn

**Files:**
- Modify: `config/seeds/prompts/dm_general.yaml`, `config/seeds/prompts/in_group.yaml` (bump version + thêm hướng dẫn)
- (Không có constant code cho 2 prompt này — store-only.)

- [ ] **Step 1:** Bump `version` cả 2 file; cập nhật `notes`. Thêm đoạn vào phần CÁCH TRA CỨU/TRẢ LỜI:
  > "Khi tin có URL hoặc cần thông tin NGOÀI kho tri thức → CHỦ ĐỘNG gọi `fetch_url` (đọc link) / `web_search` (tra web). KHÔNG tự nói 'không đọc được link' khi chưa thử tool. Sau `web_search`, đọc sâu 1 kết quả bằng `fetch_url` nếu cần. Trả lời NGẮN GỌN, đúng trọng tâm (đặc biệt khi tóm tắt link/video — tránh dài dòng)."
- [ ] **Step 2:** Reseed: `uv run python scripts/seed_prompts.py` → verify version mới active (query `prompts`).
- [ ] **Step 3:** Verify qua harness: paste link → bot tự đọc; hỏi tin tức → bot tự `web_search` (cần key Tavily cấu hình ở superadmin hoặc .env tạm).
- [ ] **Step 4: Commit**

```bash
git add config/seeds/prompts/dm_general.yaml config/seeds/prompts/in_group.yaml
git commit -m "feat(prompt): responders proactively read links + web_search, concise"
```

---

## PHASE 6 — Regression + dọn dẹp

### Task 17: Full regression + unit suite

- [ ] **Step 1:** `uv run pytest tests/unit/test_media_registry.py tests/unit/test_fetch_url.py tests/unit/test_web_extractor.py tests/unit/test_document_extractor.py tests/unit/test_tavily_provider.py tests/unit/test_web_search_tool.py tests/integration/test_platform_integrations_repo.py tests/integration/test_api_integrations.py tests/integration/test_media_enrichment.py -v` → tất cả PASS.
- [ ] **Step 2:** Harness regression: `uv run python scripts/harness.py gold` (11/11) · `multipass` (6/6) · `workload` (6/6). (Phase 5 đụng prompt → chạy lại đủ 3 bộ; nếu lệch, tune prompt giữ xanh.)
- [ ] **Step 3:** FE `cd frontend && npm run build` sạch.
- [ ] **Step 4: Commit** (nếu có fix).

### Task 18: Cập nhật BUILD LOG + dọn key tạm

- [ ] **Step 1:** Nếu Phase 3 dùng `settings.TAVILY_API_KEY` tạm: xác nhận runtime đã đọc key từ DB (Task 13); giữ env làm fallback hay gỡ tuỳ ý (ghi rõ trong BUILD LOG).
- [ ] **Step 2:** Thêm mục BUILD LOG vào `docs/architecture/system-design.md` (ngày 2026-06-xx): media reading + web_search + integration superadmin — tóm tắt + verify.
- [ ] **Step 3: Commit**

```bash
git add docs/architecture/system-design.md
git commit -m "docs: BUILD LOG media reading + web_search + integration"
```

---

## Self-review notes (cho người thực thi)
- **Vision model:** ảnh chỉ chạy nếu boss có `vision_model_id` + caps routing "vision" (gpt-5.4-mini xác nhận vision-capable trước khi dựa vào); thiếu → degrade rỗng.
- **YouTube IP-block:** server có thể bị chặn — fallback description đã có; theo dõi log, cân nhắc proxy phase sau.
- **TikTok:** chỉ metadata/description (transcript đầy đủ = ASR phase sau).
- **Không đụng WIP AI-settings** (ai-tab/own-model-drawer/boss_ai_config/api_ai/migration 0014): integration mới hoàn toàn tách biệt.
- **Đường B test:** web test channel chỉ text → dùng fixture media_url; verify thật khi cắm Zalo.

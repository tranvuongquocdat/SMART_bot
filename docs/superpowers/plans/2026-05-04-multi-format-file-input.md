# Multi-format File Input — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot reads PDF / image / DOCX inline during conversation. PDF + image stay native (OpenAI Files API for PDF, base64 image_url for images). DOCX → mammoth markdown. Sentinel-based references in `messages.content` (no schema migration). Lifetime ≈ existing 15-message recent window.

**Architecture:**
- **Channels download files locally** (Zalo bridge.js using session cookies; Telegram getFile via bot token). `Attachment.url` becomes a local path.
- **`file_ingestion`** dispatches by mime → emits sentinel strings (`[OPENAI_FILE: ...]` / `[LOCAL_IMAGE: ...]`) or inline DOCX markdown.
- **`OpenAILLMClient`** parses sentinels at LLM call time → chat.completions content parts (`{type:"file",file:{file_id}}` / `{type:"image_url",image_url:{url:"data:..."}}`).
- **Qdrant indexer** strips sentinels before embedding so RAG vectors stay clean.

**Tech Stack:** Python 3.12, AsyncOpenAI SDK 1.82+, mammoth, pypdf, node-fetch (bridge.js), httpx (telegram), pytest with `asyncio_mode = "auto"`.

**Spec:** [docs/superpowers/specs/2026-05-04-multi-format-file-input-design.md](../specs/2026-05-04-multi-format-file-input-design.md)

---

## File Map

| File | Change |
|------|--------|
| `src/utils/sentinels.py` | NEW — `strip_sentinels()`, `parse_sentinels()`, `SentinelRef` |
| `src/infrastructure/openai_files.py` | NEW — `upload()`, `delete()` with retry + `expires_after` |
| `src/infrastructure/openai_client.py` | Add `get_client()` accessor for default AsyncOpenAI |
| `src/agent/file_ingestion.py` | NEW — `ingest()` dispatch + opportunistic sweep |
| `src/infrastructure/llm/openai.py` | Sentinel → content parts in `chat_with_tools` |
| `src/agent/secretary_agent.py` | Accept `attachments` in `handle_message`; strip sentinels at index/search sites |
| `src/controllers/message_router.py` | Pass `incoming.attachments` through to `handle_message` |
| `src/channels/zalo_bridge/bridge.js` | Download attachments via cookie session, emit `local_path` |
| `src/channels/zalo_bridge/package.json` | Add `node-fetch` dep |
| `src/channels/zalo.py` | Map bridge `local_path`/`mime`/`filename`/`size_bytes` |
| `src/channels/telegram.py` | `getFile` + download photo/document; populate `Attachment` |
| `scripts/cli_test.py` | `--attach` flag |
| `pyproject.toml` | Add `mammoth>=1.6`, `pypdf>=4.0` |
| `Dockerfile` | Ensure `data/inbound/` directory at build time |
| `tests/unit/test_sentinels.py` | NEW |
| `tests/unit/test_openai_files.py` | NEW |
| `tests/unit/test_file_ingestion.py` | NEW |
| `tests/unit/test_openai_provider_sentinels.py` | NEW |
| `tests/unit/test_telegram_attachment_download.py` | NEW |

---

## Task 1: Sentinel utilities

**Files:**
- Create: `src/utils/sentinels.py`
- Test: `tests/unit/test_sentinels.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sentinels.py`:

```python
"""Sentinel parsing for inline file references in messages.content."""
from src.utils.sentinels import parse_sentinels, strip_sentinels, SentinelRef


def test_strip_returns_empty_string_unchanged():
    assert strip_sentinels("") == ""


def test_strip_no_sentinel_returns_text():
    assert strip_sentinels("hello world") == "hello world"


def test_strip_removes_whole_line_sentinel():
    text = "Tóm tắt giúp\n[OPENAI_FILE: file_id=file-x mime=application/pdf filename=a.pdf]"
    assert strip_sentinels(text) == "Tóm tắt giúp"


def test_strip_keeps_inline_lookalike():
    # Sentinel-looking text in middle of a line must not be stripped
    text = "Anh thấy chuỗi [OPENAI_FILE: file_id=x] trong log không?"
    assert strip_sentinels(text) == text


def test_strip_collapses_blank_lines():
    text = "Line A\n[LOCAL_IMAGE: path=/x mime=image/jpeg]\n\nLine B"
    assert strip_sentinels(text) == "Line A\n\nLine B"


def test_parse_no_sentinel():
    cleaned, refs = parse_sentinels("plain text")
    assert cleaned == "plain text"
    assert refs == []


def test_parse_openai_file_sentinel():
    text = "Câu hỏi\n[OPENAI_FILE: file_id=file-abc mime=application/pdf filename=invoice.pdf]"
    cleaned, refs = parse_sentinels(text)
    assert cleaned == "Câu hỏi"
    assert len(refs) == 1
    assert refs[0] == SentinelRef(
        kind="OPENAI_FILE",
        fields={"file_id": "file-abc", "mime": "application/pdf", "filename": "invoice.pdf"},
    )


def test_parse_local_image_sentinel():
    text = "[LOCAL_IMAGE: path=data/inbound/abc/1_p.jpg mime=image/jpeg]"
    cleaned, refs = parse_sentinels(text)
    assert cleaned == ""
    assert refs == [SentinelRef(
        kind="LOCAL_IMAGE",
        fields={"path": "data/inbound/abc/1_p.jpg", "mime": "image/jpeg"},
    )]


def test_parse_multiple_sentinels():
    text = (
        "So sánh 2 file\n"
        "[OPENAI_FILE: file_id=file-1 mime=application/pdf filename=a.pdf]\n"
        "[OPENAI_FILE: file_id=file-2 mime=application/pdf filename=b.pdf]"
    )
    cleaned, refs = parse_sentinels(text)
    assert cleaned == "So sánh 2 file"
    assert len(refs) == 2
    assert refs[0].fields["file_id"] == "file-1"
    assert refs[1].fields["file_id"] == "file-2"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_sentinels.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.sentinels'`.

- [ ] **Step 3: Implement `src/utils/sentinels.py`**

```python
"""Whole-line sentinel parsing for file refs in messages.content.

Format (each on its own line):
  [OPENAI_FILE: file_id=file-xxx mime=application/pdf filename=invoice.pdf]
  [LOCAL_IMAGE: path=data/inbound/abc/123_photo.jpg mime=image/jpeg]

Used by:
  • file_ingestion — emit sentinels for files attached to user message
  • infrastructure/llm/openai.py — convert sentinels to content parts at LLM call
  • Qdrant indexer — strip sentinels before embedding so RAG stays clean
"""
from __future__ import annotations

import re
from typing import NamedTuple

_SENTINEL_RE = re.compile(
    r"^\[(OPENAI_FILE|LOCAL_IMAGE):\s+(.+)\]$",
    re.MULTILINE,
)
_KV_RE = re.compile(r"(\w+)=(\S+)")


class SentinelRef(NamedTuple):
    kind: str
    fields: dict[str, str]


def strip_sentinels(text: str) -> str:
    """Remove whole-line sentinels; leave inline-typed lookalikes alone."""
    if not text:
        return text
    cleaned = _SENTINEL_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def parse_sentinels(text: str) -> tuple[str, list[SentinelRef]]:
    """Return (cleaned_text, refs)."""
    if not text:
        return text, []
    refs: list[SentinelRef] = []
    for m in _SENTINEL_RE.finditer(text):
        fields = dict(_KV_RE.findall(m.group(2)))
        refs.append(SentinelRef(kind=m.group(1), fields=fields))
    return strip_sentinels(text), refs
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/unit/test_sentinels.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/utils/sentinels.py tests/unit/test_sentinels.py
git commit -m "feat(utils): sentinel parser for inline file refs

[OPENAI_FILE: ...] / [LOCAL_IMAGE: ...] whole-line sentinels — used
by file_ingestion, OpenAI LLM provider, and Qdrant indexer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: OpenAI Files API wrapper

**Files:**
- Create: `src/infrastructure/openai_files.py`
- Modify: `src/infrastructure/openai_client.py` (add `get_client()` accessor)
- Test: `tests/unit/test_openai_files.py`

- [ ] **Step 1: Add `get_client()` to `openai_client.py`**

Open `src/infrastructure/openai_client.py`, append at end:

```python
def get_client() -> AsyncOpenAI:
    """Return the initialized default AsyncOpenAI client.

    File uploads (openai_files.upload) currently use this default client
    rather than per-boss credentials — acceptable for ephemeral file refs.
    """
    if _client is None:
        raise RuntimeError("openai client not initialized — call init_openai first")
    return _client
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_openai_files.py`:

```python
"""openai_files wrapper: upload with retry + expires_after; best-effort delete."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure import openai_files


def _mock_client_with_upload(file_id: str = "file-abc"):
    client = MagicMock()
    client.files = MagicMock()
    resp = MagicMock()
    resp.id = file_id
    client.files.create = AsyncMock(return_value=resp)
    client.files.delete = AsyncMock()
    return client


async def test_upload_returns_file_id(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    client = _mock_client_with_upload("file-xyz")
    fid = await openai_files.upload(client, p, "application/pdf", "x.pdf")
    assert fid == "file-xyz"
    client.files.create.assert_awaited_once()
    kwargs = client.files.create.await_args.kwargs
    assert kwargs["purpose"] == "user_data"
    assert kwargs["expires_after"] == {"anchor": "created_at", "seconds": 30 * 24 * 3600}


async def test_upload_retries_on_5xx(tmp_path):
    from openai import APIError
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4")

    client = MagicMock()
    client.files = MagicMock()
    err = APIError("server boom", request=MagicMock(), body=None)
    err.status_code = 500
    ok = MagicMock()
    ok.id = "file-after-retry"
    client.files.create = AsyncMock(side_effect=[err, err, ok])

    with patch("src.infrastructure.openai_files.asyncio.sleep", new=AsyncMock()):
        fid = await openai_files.upload(client, p, "application/pdf", "x.pdf")
    assert fid == "file-after-retry"
    assert client.files.create.await_count == 3


async def test_upload_does_not_retry_on_4xx(tmp_path):
    from openai import APIError
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4")

    client = MagicMock()
    client.files = MagicMock()
    err = APIError("bad mime", request=MagicMock(), body=None)
    err.status_code = 415
    client.files.create = AsyncMock(side_effect=err)

    with patch("src.infrastructure.openai_files.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(APIError):
            await openai_files.upload(client, p, "application/pdf", "x.pdf")
    assert client.files.create.await_count == 1


async def test_delete_swallows_errors():
    client = _mock_client_with_upload()
    client.files.delete = AsyncMock(side_effect=Exception("not found"))
    # Should not raise.
    await openai_files.delete(client, "file-x")
    client.files.delete.assert_awaited_once_with("file-x")
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/unit/test_openai_files.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `src/infrastructure/openai_files.py`**

```python
"""OpenAI Files API wrapper.

Uploads use purpose='user_data' with expires_after=30 days so OpenAI
auto-deletes orphan files. Caller does not need cleanup cron.

Retry policy: 3 attempts on 5xx / 429 / network with exponential backoff.
4xx other than 429 raises immediately (bad input).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIError, RateLimitError

logger = logging.getLogger("openai_files")

_BACKOFFS = (0.2, 1.0, 5.0)
_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RateLimitError, APIConnectionError, APIError,
)
_EXPIRES_SECONDS = 30 * 24 * 3600


async def upload(
    client: Any, path: str | Path, mime: str, filename: str,
) -> str:
    """Upload a local file, return OpenAI file_id."""
    path = Path(path)
    last_exc: Exception | None = None
    for i, backoff in enumerate((0.0,) + _BACKOFFS):
        if backoff:
            await asyncio.sleep(backoff)
        try:
            with path.open("rb") as fh:
                resp = await client.files.create(
                    file=(filename, fh, mime),
                    purpose="user_data",
                    expires_after={
                        "anchor": "created_at",
                        "seconds": _EXPIRES_SECONDS,
                    },
                )
            return resp.id
        except _RETRY_EXCEPTIONS as e:
            last_exc = e
            status = getattr(e, "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                raise
            logger.warning(
                "openai_files.upload attempt %d for %s failed: %s",
                i + 1, filename, e,
            )
    assert last_exc is not None
    raise last_exc


async def delete(client: Any, file_id: str) -> None:
    """Best-effort delete; logs but never raises."""
    try:
        await client.files.delete(file_id)
    except Exception as e:
        logger.warning("openai_files.delete(%s) failed: %s", file_id, e)
```

- [ ] **Step 5: Run tests to verify pass**

```
pytest tests/unit/test_openai_files.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/infrastructure/openai_files.py src/infrastructure/openai_client.py tests/unit/test_openai_files.py
git commit -m "feat(infra): OpenAI Files API wrapper with retry + expires_after

Upload returns file_id with 30-day expires_after so OpenAI prunes
orphan files. Retries 5xx/429/network with backoff (0.2/1/5s).
4xx fails fast.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add `mammoth` and `pypdf` deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps**

In `pyproject.toml`, under `[project] dependencies`, add:

```toml
    "mammoth>=1.6",
    "pypdf>=4.0",
```

- [ ] **Step 2: Install + verify imports**

```bash
pip install -e .
python -c "import mammoth, pypdf; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add mammoth + pypdf for DOCX/PDF ingestion

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `file_ingestion` module

**Files:**
- Create: `src/agent/file_ingestion.py`
- Test: `tests/unit/test_file_ingestion.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_file_ingestion.py`:

```python
"""file_ingestion: dispatch attachments to sentinels / inline markdown."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agent import file_ingestion
from src.channels.base import Attachment


def _att(path: str, mime: str, name: str, size: int = 0) -> Attachment:
    return Attachment(
        kind="file", url=path, mime_type=mime, filename=name, size_bytes=size,
    )


async def test_empty_returns_empty():
    assert await file_ingestion.ingest(object(), [], "conv-1") == ""


async def test_image_emits_local_image_sentinel(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff")
    out = await file_ingestion.ingest(
        object(), [_att(str(p), "image/jpeg", "photo.jpg", size=3)], "conv-1",
    )
    assert out == f"[LOCAL_IMAGE: path={p} mime=image/jpeg]"


async def test_image_too_large(tmp_path):
    p = tmp_path / "big.jpg"
    p.write_bytes(b"x")
    big = _att(str(p), "image/jpeg", "big.jpg", size=21 * 1024 * 1024)
    out = await file_ingestion.ingest(object(), [big], "conv-1")
    assert "ảnh quá to" in out


async def test_pdf_uploads_and_emits_sentinel(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4 fake")

    fake_reader = type("R", (), {"is_encrypted": False, "pages": [None] * 3})()
    with patch("src.agent.file_ingestion.pypdf.PdfReader", return_value=fake_reader), \
         patch("src.agent.file_ingestion.openai_files.upload",
               new=AsyncMock(return_value="file-xyz")):
        out = await file_ingestion.ingest(
            object(), [_att(str(p), "application/pdf", "x.pdf", size=12)], "conv-1",
        )
    assert out == "[OPENAI_FILE: file_id=file-xyz mime=application/pdf filename=x.pdf]"
    assert not p.exists(), "local PDF should be deleted after upload"


async def test_pdf_over_page_cap(tmp_path):
    p = tmp_path / "long.pdf"
    p.write_bytes(b"%PDF")
    fake_reader = type("R", (), {"is_encrypted": False, "pages": [None] * 25})()
    with patch("src.agent.file_ingestion.pypdf.PdfReader", return_value=fake_reader):
        out = await file_ingestion.ingest(
            object(), [_att(str(p), "application/pdf", "long.pdf", size=12)], "conv-1",
        )
    assert "PDF dài >20 trang" in out


async def test_pdf_encrypted(tmp_path):
    p = tmp_path / "enc.pdf"
    p.write_bytes(b"%PDF")
    fake_reader = type("R", (), {"is_encrypted": True, "pages": []})()
    with patch("src.agent.file_ingestion.pypdf.PdfReader", return_value=fake_reader):
        out = await file_ingestion.ingest(
            object(), [_att(str(p), "application/pdf", "enc.pdf", size=4)], "conv-1",
        )
    assert "có password" in out


async def test_docx_inlines_markdown_truncated(tmp_path):
    p = tmp_path / "doc.docx"
    p.write_bytes(b"PK")  # mammoth is mocked
    big_md = "x" * (25 * 1024)
    fake_result = type("R", (), {"value": big_md})()
    with patch("src.agent.file_ingestion._mammoth_convert", return_value=big_md):
        out = await file_ingestion.ingest(
            object(), [_att(str(p), file_ingestion.DOCX_MIME, "doc.docx", size=2)], "conv-1",
        )
    assert out.startswith("[Tệp doc.docx]\n")
    body = out.split("\n", 1)[1]
    assert len(body) <= 20 * 1024 + 100  # truncate + suffix
    assert "10 trang đầu" in body
    assert not p.exists()


async def test_unsupported_mime(tmp_path):
    p = tmp_path / "data.xlsx"
    p.write_bytes(b"PK")
    out = await file_ingestion.ingest(
        object(), [_att(str(p), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data.xlsx", size=2)], "conv-1",
    )
    assert "chưa hỗ trợ" in out
    assert ".xlsx" in out


async def test_concurrent_partial_failure(tmp_path):
    img = tmp_path / "ok.jpg"; img.write_bytes(b"\xff\xd8")
    pdf = tmp_path / "bad.pdf"; pdf.write_bytes(b"%PDF")
    atts = [
        _att(str(img), "image/jpeg", "ok.jpg", size=2),
        _att(str(pdf), "application/pdf", "bad.pdf", size=4),
    ]
    fake_reader = type("R", (), {"is_encrypted": False, "pages": [None]})()
    with patch("src.agent.file_ingestion.pypdf.PdfReader", return_value=fake_reader), \
         patch("src.agent.file_ingestion.openai_files.upload",
               new=AsyncMock(side_effect=Exception("boom"))):
        out = await file_ingestion.ingest(object(), atts, "conv-1")
    parts = out.split("\n")
    assert any("LOCAL_IMAGE" in p for p in parts), "image still emitted"
    assert any("tạm thời lỗi" in p for p in parts), "pdf failure surfaced"


async def test_filename_sanitize_in_pdf_sentinel(tmp_path):
    # Filename only appears in OPENAI_FILE sentinel (LOCAL_IMAGE is path-only).
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF")
    fake_reader = type("R", (), {"is_encrypted": False, "pages": [None]})()
    with patch("src.agent.file_ingestion.pypdf.PdfReader", return_value=fake_reader), \
         patch("src.agent.file_ingestion.openai_files.upload",
               new=AsyncMock(return_value="file-z")):
        weird = _att(str(p), "application/pdf", "Báo cáo Q1/2026.pdf", size=4)
        out = await file_ingestion.ingest(object(), [weird], "conv-1")
    assert "filename=Báo cáo Q1_2026.pdf" in out


async def test_sweep_old_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "data" / "inbound" / "conv-1"
    base.mkdir(parents=True)
    old = base / "old.bin"
    old.write_bytes(b"x")
    import os, time
    old_mtime = time.time() - (25 * 3600)
    os.utime(old, (old_mtime, old_mtime))
    fresh = base / "fresh.bin"
    fresh.write_bytes(b"y")
    await file_ingestion.ingest(object(), [], "conv-1")
    # ingest with [] returns early; sweep only runs when attachments present.
    assert old.exists() and fresh.exists()
    # Now with an attachment the sweep should fire:
    img = base / "img.jpg"
    img.write_bytes(b"\xff")
    att = _att(str(img), "image/jpeg", "img.jpg", size=1)
    await file_ingestion.ingest(object(), [att], "conv-1")
    assert not old.exists(), "24h-old file should be swept"
    assert fresh.exists(), "recent file kept"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_file_ingestion.py -v
```

Expected: FAIL on import (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/agent/file_ingestion.py`**

```python
"""Convert IncomingMessage attachments to a text block with sentinels.

Per-mime dispatch:
  • image/*           → [LOCAL_IMAGE: ...] sentinel; file kept on disk for
                        re-base64 each turn (lifetime ~ 15-message window)
  • application/pdf   → upload Files API → [OPENAI_FILE: ...] sentinel;
                        local file deleted post-upload
  • DOCX              → mammoth → markdown inline, truncated at 20KB;
                        local file deleted post-extract
  • other             → "[Tệp <name> — chưa hỗ trợ định dạng .xxx]"

Opportunistic sweep on each non-empty call: deletes files in
data/inbound/<conv_id>/ older than 24h to avoid orphan accumulation.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import mammoth
import pypdf

from src.channels.base import Attachment
from src.infrastructure import openai_files

logger = logging.getLogger("file_ingestion")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"

_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_PDF_BYTES = 32 * 1024 * 1024
_MAX_PDF_PAGES = 20
_MAX_DOCX_BYTES = 5 * 1024 * 1024
_MAX_DOCX_OUTPUT = 20 * 1024
_LOCAL_FILE_TTL_SEC = 24 * 3600


def _safe_name(filename: str) -> str:
    name = unicodedata.normalize("NFC", filename or "file")
    name = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", name)
    if "." in name:
        base, ext = name.rsplit(".", 1)
        return f"{base[:80]}.{ext[:20]}"
    return name[:80]


async def ingest(
    openai_client: Any, attachments: list[Attachment], conv_id: str,
) -> str:
    if not attachments:
        return ""
    _sweep_old_files(conv_id)
    parts = await asyncio.gather(*[_one(openai_client, a) for a in attachments])
    return "\n".join(p for p in parts if p)


async def _one(client: Any, a: Attachment) -> str:
    name = _safe_name(a.filename or "tệp")
    mime = a.mime_type or ""
    if not a.url:
        return f"[Tệp {name} — không tải được]"
    if mime.startswith("image/"):
        return _ingest_image(a, name)
    if mime == PDF_MIME:
        return await _ingest_pdf(client, a, name)
    if mime == DOCX_MIME:
        return await _ingest_docx(a, name)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "?"
    return f"[Tệp {name} — chưa hỗ trợ định dạng .{ext}]"


def _ingest_image(a: Attachment, name: str) -> str:
    if a.size_bytes > _MAX_IMAGE_BYTES:
        return f"[Tệp {name} — ảnh quá to (>20MB)]"
    return f"[LOCAL_IMAGE: path={a.url} mime={a.mime_type}]"


async def _ingest_pdf(client: Any, a: Attachment, name: str) -> str:
    if a.size_bytes > _MAX_PDF_BYTES:
        return f"[Tệp {name} — PDF quá lớn (>32MB)]"
    try:
        reader = pypdf.PdfReader(a.url)
        if reader.is_encrypted:
            return f"[Tệp {name} — file có password]"
        pages = len(reader.pages)
    except Exception as e:
        logger.warning("pypdf inspect %s failed: %s", a.url, e)
        return f"[Tệp {name} — không đọc được file]"
    if pages > _MAX_PDF_PAGES:
        return (
            f"[Tệp {name} — PDF dài >20 trang, em chỉ đọc được file ngắn hơn; "
            f"cắt giúp anh hoặc gửi DOCX]"
        )
    try:
        file_id = await openai_files.upload(client, a.url, a.mime_type, name)
    except Exception as e:
        logger.warning("openai_files.upload %s failed: %s", name, e)
        return f"[Tệp {name} — tạm thời lỗi, gửi lại giúp anh]"
    _try_delete(a.url)
    return f"[OPENAI_FILE: file_id={file_id} mime={a.mime_type} filename={name}]"


async def _ingest_docx(a: Attachment, name: str) -> str:
    if a.size_bytes > _MAX_DOCX_BYTES:
        return f"[Tệp {name} — DOCX quá lớn (>5MB)]"
    try:
        md = await asyncio.to_thread(_mammoth_convert, a.url)
    except Exception as e:
        logger.warning("mammoth %s failed: %s", a.url, e)
        return f"[Tệp {name} — không đọc được file]"
    if len(md) > _MAX_DOCX_OUTPUT:
        md = md[:_MAX_DOCX_OUTPUT] + "\n…(file dài, em chỉ đọc ~10 trang đầu)"
    _try_delete(a.url)
    return f"[Tệp {name}]\n{md}"


def _mammoth_convert(path: str) -> str:
    with open(path, "rb") as fh:
        return mammoth.convert_to_markdown(fh).value


def _try_delete(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _sweep_old_files(conv_id: str) -> None:
    base = Path("data/inbound") / str(conv_id)
    if not base.exists():
        return
    cutoff = time.time() - _LOCAL_FILE_TTL_SEC
    for p in base.iterdir():
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/unit/test_file_ingestion.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/agent/file_ingestion.py tests/unit/test_file_ingestion.py
git commit -m "feat(agent): file_ingestion dispatch — image/PDF/DOCX → sentinels

PDF uploaded once via Files API, sentinel stored in messages.content;
local file deleted post-upload. Image kept on disk for re-base64.
DOCX inlined as mammoth markdown (truncated 20KB ~ 10 pages).
Opportunistic 24h sweep prevents orphan accumulation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: OpenAI provider sentinel parsing

**Files:**
- Modify: `src/infrastructure/llm/openai.py`
- Test: `tests/unit/test_openai_provider_sentinels.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_openai_provider_sentinels.py`:

```python
"""OpenAILLMClient parses sentinels into chat.completions content parts."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.llm.openai import _inject_file_parts, _ref_to_part
from src.utils.sentinels import SentinelRef


def test_no_sentinel_passthrough():
    msg = {"role": "user", "content": "plain hello"}
    out = _inject_file_parts(msg)
    assert out is msg or out == msg
    assert out.get("content") == "plain hello"


def test_assistant_with_string_passthrough():
    msg = {"role": "assistant", "content": "OK đã ghi note rồi anh"}
    out = _inject_file_parts(msg)
    assert out["content"] == "OK đã ghi note rồi anh"


def test_openai_file_sentinel_becomes_file_part():
    msg = {
        "role": "user",
        "content": "Tóm tắt giúp\n[OPENAI_FILE: file_id=file-xx mime=application/pdf filename=a.pdf]",
    }
    out = _inject_file_parts(msg)
    assert out["content"] == [
        {"type": "text", "text": "Tóm tắt giúp"},
        {"type": "file", "file": {"file_id": "file-xx"}},
    ]


def test_local_image_sentinel_becomes_image_url(tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(b"\xff\xd8\xffhello")
    msg = {
        "role": "user",
        "content": f"đọc giúp\n[LOCAL_IMAGE: path={img} mime=image/jpeg]",
    }
    out = _inject_file_parts(msg)
    parts = out["content"]
    assert parts[0] == {"type": "text", "text": "đọc giúp"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_local_image_missing_falls_back_to_text():
    msg = {
        "role": "user",
        "content": "[LOCAL_IMAGE: path=/tmp/does-not-exist.jpg mime=image/jpeg]",
    }
    out = _inject_file_parts(msg)
    assert out["content"] == [{"type": "text", "text": "[Ảnh đã hết hạn]"}]


def test_non_string_content_passthrough():
    msg = {"role": "tool", "content": "raw tool output"}
    msg2 = {"role": "user", "content": [{"type": "text", "text": "already parts"}]}
    assert _inject_file_parts(msg) == msg
    assert _inject_file_parts(msg2) == msg2
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_openai_provider_sentinels.py -v
```

Expected: FAIL with `ImportError: cannot import name '_inject_file_parts'`.

- [ ] **Step 3: Modify `src/infrastructure/llm/openai.py`**

Replace entire file content:

```python
"""OpenAI implementation of LLMClient.

Each instance owns its own AsyncOpenAI client + model choices. At call
time, sentinels in message content (`[OPENAI_FILE: ...]` /
`[LOCAL_IMAGE: ...]`) are expanded into chat.completions content parts.
Messages without sentinels pass through unchanged.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from src.infrastructure.llm.base import LLMClient
from src.utils.sentinels import SentinelRef, parse_sentinels

logger = logging.getLogger("llm.openai")


class OpenAILLMClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        embedding_dim: int,
    ) -> None:
        self._api_key = api_key
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        processed = [_inject_file_parts(m) for m in messages]
        call_kwargs: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": processed,
            **kwargs,
        }
        if tools:
            call_kwargs["tools"] = tools
        response = await self._client.chat.completions.create(**call_kwargs)
        usage = response.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        } if usage else {}
        return response.choices[0].message, usage_dict

    async def embed(self, text: str) -> tuple[list[float], int]:
        response = await self._client.embeddings.create(
            input=text, model=self._embedding_model,
        )
        return response.data[0].embedding, self._embedding_dim


def _inject_file_parts(msg: dict) -> dict:
    """Replace string content with content-parts list when sentinels present."""
    content = msg.get("content")
    if not isinstance(content, str):
        return msg
    cleaned, refs = parse_sentinels(content)
    if not refs:
        return msg
    parts: list[dict] = []
    if cleaned:
        parts.append({"type": "text", "text": cleaned})
    for ref in refs:
        part = _ref_to_part(ref)
        if part:
            parts.append(part)
    return {**msg, "content": parts}


def _ref_to_part(ref: SentinelRef) -> dict | None:
    if ref.kind == "OPENAI_FILE":
        fid = ref.fields.get("file_id")
        if not fid:
            return None
        return {"type": "file", "file": {"file_id": fid}}
    if ref.kind == "LOCAL_IMAGE":
        path = ref.fields.get("path")
        mime = ref.fields.get("mime", "image/jpeg")
        if not path or not Path(path).exists():
            return {"type": "text", "text": "[Ảnh đã hết hạn]"}
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            logger.warning("read local image %s failed: %s", path, e)
            return {"type": "text", "text": "[Ảnh đã hết hạn]"}
        b64 = base64.b64encode(data).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    return None
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/unit/test_openai_provider_sentinels.py tests/unit/test_sentinels.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/infrastructure/llm/openai.py tests/unit/test_openai_provider_sentinels.py
git commit -m "feat(llm): OpenAI provider expands sentinels to content parts

[OPENAI_FILE: ...] → {type:'file', file:{file_id}}
[LOCAL_IMAGE: ...] → {type:'image_url', image_url:{url:'data:...'}} (lazy b64)
Missing local image → [Ảnh đã hết hạn] text fallback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Wire `secretary_agent` + `message_router` for attachments

**Files:**
- Modify: `src/agent/secretary_agent.py`
- Modify: `src/controllers/message_router.py`

- [ ] **Step 1: Modify router to pass attachments**

Open `src/controllers/message_router.py`. In `MessageRouter.handle`, locate the `await handle_message(...)` call (around line 61). Add `attachments=incoming.attachments` keyword arg:

```python
await handle_message(
    incoming.text or "",
    incoming.chat_id,
    incoming.sender_id or None,
    incoming.chat_type == "group",
    incoming.is_mentioned,
    incoming.group_name,
    sender_name=incoming.sender_name,
    mentions=incoming.mentions,
    username_mentions=incoming.username_mentions,
    reply_to=reply_to,
    new_members=incoming.new_members,
    attachments=incoming.attachments,
)
```

- [ ] **Step 2: Modify `handle_message` signature**

Open `src/agent/secretary_agent.py`. In `handle_message` (line 311), add the `attachments` keyword parameter at the end of the keyword-only group:

```python
async def handle_message(
    text: str,
    chat_id: str,
    sender_id: str,
    is_group: bool,
    bot_mentioned: bool,
    group_name: str = "",
    *,
    sender_name: str = "",
    mentions: list[dict] | None = None,
    username_mentions: list[str] | None = None,
    reply_to: dict | None = None,
    new_members: list[dict] | None = None,
    attachments: list | None = None,
):
```

- [ ] **Step 3: Enrich text from attachments + strip sentinels at index sites**

Inside `handle_message`, just after the input log line (`logger.info("%s >>> INPUT: %s", log_prefix, text[:200])`), add:

```python
    # ---- Step 0: Ingest file attachments → sentinels appended to text ----
    if attachments:
        from src.agent.file_ingestion import ingest as _ingest_files
        from src.infrastructure import openai_client as _openai_client_mod
        try:
            ingested = await _ingest_files(
                _openai_client_mod.get_client(), attachments, chat_id,
            )
            if ingested:
                text = (text + "\n\n" + ingested).strip() if text else ingested
                logger.info("%s file attachments ingested (%d)", log_prefix, len(attachments))
        except Exception:
            logger.exception("%s file_ingestion failed", log_prefix)
```

Now wrap the 3 indexing sites. Use the helper `strip_sentinels`. Add at top of file (with other imports):

```python
from src.utils.sentinels import strip_sentinels
```

**Site 1 — group routing (around line 358)**, replace the existing `vector, _dim = await _llm.embed(text)` block. Find:

```python
                msg_id = await db.save_message(chat_id, "user", text, sender_id)
                _boss_row = await db.get_boss(boss_id) or {}
                _llm = get_llm_client(_boss_row, _settings or Settings())
                vector, _dim = await _llm.embed(text)
                asyncio.create_task(
                    qdrant.upsert(
                        collection=f"messages_{boss_id}_{_dim}",
                        point_id=msg_id,
                        chat_id=chat_id,
                        role="user",
                        text=text,
                        vector=vector,
                    )
```

Replace with:

```python
                msg_id = await db.save_message(chat_id, "user", text, sender_id)
                _boss_row = await db.get_boss(boss_id) or {}
                _llm = get_llm_client(_boss_row, _settings or Settings())
                _clean = strip_sentinels(text)
                vector, _dim = await _llm.embed(_clean)
                asyncio.create_task(
                    qdrant.upsert(
                        collection=f"messages_{boss_id}_{_dim}",
                        point_id=msg_id,
                        chat_id=chat_id,
                        role="user",
                        text=_clean,
                        vector=vector,
                    )
```

**Site 2 — main user-message save (around line 415)**, find:

```python
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        llm = await get_llm_for_ctx(ctx)
        vector, _ = await llm.embed(text)
        asyncio.create_task(
            qdrant.upsert(
                collection=ctx.messages_collection,
                point_id=msg_id,
                chat_id=chat_id,
                role="user",
                text=text,
                vector=vector,
            )
        )
```

Replace with:

```python
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        llm = await get_llm_for_ctx(ctx)
        _clean_user = strip_sentinels(text)
        vector, _ = await llm.embed(_clean_user)
        asyncio.create_task(
            qdrant.upsert(
                collection=ctx.messages_collection,
                point_id=msg_id,
                chat_id=chat_id,
                role="user",
                text=_clean_user,
                vector=vector,
            )
        )
```

**Site 3 — RAG search query (in `_build_turn_messages`, around line 256)**, find:

```python
        qdrant.search(
            collection=ctx.messages_collection,
            query=text,
            chat_id=chat_id,
            top_n=_settings.rag_messages,
        ),
```

Replace with:

```python
        qdrant.search(
            collection=ctx.messages_collection,
            query=strip_sentinels(text),
            chat_id=chat_id,
            top_n=_settings.rag_messages,
        ),
```

(Assistant reply indexing site at line 521 doesn't need stripping — assistant text never contains sentinels — but add it for symmetry/safety. Find `vector, _ = await llm.embed(reply_text)` and prefix with `_clean_reply = strip_sentinels(reply_text)`; pass `_clean_reply` to embed and to upsert's `text=` arg.)

- [ ] **Step 4: Smoke-import**

```
python -c "from src.agent.secretary_agent import handle_message; print('ok')"
python -c "from src.controllers.message_router import MessageRouter; print('ok')"
```

Expected: both `ok`.

- [ ] **Step 5: Run existing router test**

```
pytest tests/unit/test_message_router.py -v
```

Expected: existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/agent/secretary_agent.py src/controllers/message_router.py
git commit -m "feat(agent): wire attachments through router + strip sentinels at index/search

handle_message accepts attachments=, calls file_ingestion.ingest() to
append sentinel block to user text. RAG search query and Qdrant
upsert text/vector all use strip_sentinels() so embeddings stay clean.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Telegram channel — download photo/document

**Files:**
- Modify: `src/channels/telegram.py`
- Test: `tests/unit/test_telegram_attachment_download.py`

- [ ] **Step 1: Read existing structure**

Open `src/channels/telegram.py` and locate:
- The HTTP client used (`httpx.AsyncClient` instance variable, e.g. `self._http`)
- Bot token (`self._token` or similar)
- The `_to_incoming` method around line 194 where attachments are detected

Note the actual attribute names — the next step uses placeholder names that may differ.

- [ ] **Step 2: Add download helper at module level**

Add near the top of `src/channels/telegram.py` (after imports):

```python
import os
import re
import unicodedata
from pathlib import Path

_INBOUND_ROOT = Path("data/inbound")


def _safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name or "file")
    name = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", name)
    if "." in name:
        base, ext = name.rsplit(".", 1)
        return f"{base[:80]}.{ext[:20]}"
    return name[:80]


async def _download_to_disk(
    http_client, bot_token: str, file_id: str,
    chat_id: str, msg_id: str, filename: str,
) -> str:
    """Telegram getFile + GET file. Returns local path or '' on failure."""
    try:
        r = await http_client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            return ""
        file_path = body["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        r2 = await http_client.get(url)
        r2.raise_for_status()
        d = _INBOUND_ROOT / chat_id
        d.mkdir(parents=True, exist_ok=True)
        local = d / f"{msg_id}_{_safe_filename(filename)}"
        local.write_bytes(r2.content)
        return str(local)
    except Exception:
        import logging
        logging.getLogger("channels.telegram").warning(
            "telegram download failed for file_id=%s", file_id, exc_info=True,
        )
        return ""
```

- [ ] **Step 3: Update attachment harvest in `_to_incoming` (around line 194)**

Find:

```python
        attachments: list[Attachment] = []
        if message.get("photo"):
            attachments.append(Attachment(kind="photo"))
        if message.get("voice"):
            attachments.append(Attachment(kind="voice"))
        if message.get("document"):
            doc = message["document"]
            attachments.append(Attachment(
                kind="file",
                filename=doc.get("file_name", ""),
                mime_type=doc.get("mime_type", ""),
                size_bytes=doc.get("file_size", 0),
            ))
```

Replace with:

```python
        attachments: list[Attachment] = []
        msg_id_str = str(message.get("message_id", ""))
        chat_id_str = str(chat_id)
        if message.get("photo"):
            photos = message["photo"]
            largest = photos[-1]
            unique = largest.get("file_unique_id", largest.get("file_id", "p"))
            name = f"{unique}.jpg"
            local = await _download_to_disk(
                self._http, self._token, largest["file_id"],
                chat_id_str, msg_id_str, name,
            )
            attachments.append(Attachment(
                kind="photo",
                url=local,
                mime_type="image/jpeg",
                filename=name,
                size_bytes=int(largest.get("file_size", 0)),
            ))
        if message.get("voice"):
            attachments.append(Attachment(kind="voice"))  # voice out of scope
        if message.get("document"):
            doc = message["document"]
            name = doc.get("file_name") or f"doc_{doc.get('file_unique_id', '')}"
            local = await _download_to_disk(
                self._http, self._token, doc["file_id"],
                chat_id_str, msg_id_str, name,
            )
            attachments.append(Attachment(
                kind="file",
                url=local,
                filename=name,
                mime_type=doc.get("mime_type", ""),
                size_bytes=int(doc.get("file_size", 0)),
            ))
```

(Adjust `self._http` and `self._token` to the actual attribute names found in step 1.)

- [ ] **Step 4: Write the test**

Create `tests/unit/test_telegram_attachment_download.py`:

```python
"""Telegram channel: download photo/document via getFile + GET."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.channels import telegram as tg


async def test_download_to_disk_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    getfile_resp = MagicMock()
    getfile_resp.raise_for_status = MagicMock()
    getfile_resp.json.return_value = {"ok": True, "result": {"file_path": "photos/x.jpg"}}
    bytes_resp = MagicMock()
    bytes_resp.raise_for_status = MagicMock()
    bytes_resp.content = b"\xff\xd8\xff\xe0image-bytes"

    http = MagicMock()
    http.get = AsyncMock(side_effect=[getfile_resp, bytes_resp])

    local = await tg._download_to_disk(
        http, "BOT_TOKEN", "FID", "chat-1", "msg-1", "x.jpg",
    )
    assert local
    p = Path(local)
    assert p.exists()
    assert p.read_bytes() == b"\xff\xd8\xff\xe0image-bytes"
    assert p.parent == Path("data/inbound/chat-1")


async def test_download_to_disk_returns_empty_on_getfile_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = MagicMock()
    bad.raise_for_status = MagicMock()
    bad.json.return_value = {"ok": False, "description": "file too big"}
    http = MagicMock(); http.get = AsyncMock(return_value=bad)
    local = await tg._download_to_disk(
        http, "BOT", "FID", "chat-1", "msg-1", "x.pdf",
    )
    assert local == ""


def test_safe_filename_normalizes_vietnamese():
    assert tg._safe_filename("Báo cáo Q1/2026.docx") == "Báo cáo Q1_2026.docx"
    assert tg._safe_filename("../etc/passwd") == ".._etc_passwd"
```

- [ ] **Step 5: Run tests to verify pass**

```
pytest tests/unit/test_telegram_attachment_download.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/channels/telegram.py tests/unit/test_telegram_attachment_download.py
git commit -m "feat(telegram): download photo/document via getFile

Telegram channel now hydrates Attachment.url with a local disk path
under data/inbound/<chat_id>/. Voice still detected but ignored
(out of scope).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Zalo bridge.js — download with session cookies

**Files:**
- Modify: `src/channels/zalo_bridge/bridge.js`
- Modify: `src/channels/zalo_bridge/package.json`
- Modify: `src/channels/zalo.py`

- [ ] **Step 1: Add `node-fetch` dep**

In `src/channels/zalo_bridge/`:

```bash
cd src/channels/zalo_bridge && npm install node-fetch@^3 && cd -
```

Verify `package.json` shows `"node-fetch": "^3.x"` under `dependencies`.

- [ ] **Step 2: Modify `bridge.js`**

Open `src/channels/zalo_bridge/bridge.js`. Add near the top (after existing requires):

```js
const fetch = require('node-fetch').default || require('node-fetch');
const path = require('path');
const fsExtra = require('fs');

const INBOUND_ROOT = path.resolve(__dirname, '..', '..', '..', 'data', 'inbound');
let cookieHeader = '';

function buildCookieHeader(session) {
  const c = session.cookie;
  if (!c) return '';
  if (typeof c === 'string') return c;
  if (Array.isArray(c)) return c.map(x => `${x.name}=${x.value}`).join('; ');
  return '';
}

const EXT_TO_MIME = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
  gif: 'image/gif', webp: 'image/webp', heic: 'image/heic',
};

function inferMime(filename, kind) {
  const ext = (filename.split('.').pop() || '').toLowerCase();
  if (EXT_TO_MIME[ext]) return EXT_TO_MIME[ext];
  if (kind === 'image') return 'image/jpeg';
  return 'application/octet-stream';
}

function safeName(name) {
  return String(name || 'file')
    .replace(/[/\\<>:"|?*\x00-\x1f]/g, '_')
    .slice(0, 100);
}

async function downloadAttachment(href, threadId, msgId, filename) {
  const dir = path.join(INBOUND_ROOT, String(threadId));
  fsExtra.mkdirSync(dir, { recursive: true });
  const local = path.join(dir, `${msgId}_${safeName(filename)}`);
  const headers = { 'User-Agent': 'Mozilla/5.0' };
  if (cookieHeader) headers['Cookie'] = cookieHeader;
  const resp = await fetch(href, { headers });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const buf = Buffer.from(await resp.arrayBuffer());
  fsExtra.writeFileSync(local, buf);
  return { local_path: local, size_bytes: buf.length };
}
```

In `init()` after `const session = JSON.parse(...)`, add:

```js
  cookieHeader = buildCookieHeader(session);
```

Change `normalize` to async and update the listener to `await` it. Find:

```js
function normalize(msg, ownId) {
```

Change to:

```js
async function normalize(msg, ownId) {
```

Inside `normalize`, replace the existing `if (content.href)` block:

```js
    if (content.href) {
      attachments.push({ kind: contentType, href: content.href });
    }
```

…with:

```js
    if (content.href) {
      const params = content.params || {};
      const fileName = params.fileName || content.title || 'file';
      const mime = inferMime(fileName, contentType);
      const att = { kind: contentType, mime, filename: fileName };
      try {
        const dl = await downloadAttachment(
          content.href,
          threadId,
          String(data.msgId || data.cliMsgId || Date.now()),
          fileName,
        );
        att.local_path = dl.local_path;
        att.size_bytes = Number(params.totalSize || dl.size_bytes || 0);
      } catch (err) {
        att.error = String((err && err.message) || err);
        logErr('download', err, { href: content.href, fileName });
      }
      attachments.push(att);
    }
```

Update listener — find:

```js
  api.listener.on('message', (msg) => {
    try {
      const norm = normalize(msg, ownId);
      if (norm.sender_uid === ownId) return;
      emit({ event: 'message', data: norm });
    } catch (err) {
      logErr('normalize', err);
    }
  });
```

Replace with:

```js
  api.listener.on('message', async (msg) => {
    try {
      const norm = await normalize(msg, ownId);
      if (norm.sender_uid === ownId) return;
      emit({ event: 'message', data: norm });
    } catch (err) {
      logErr('normalize', err);
    }
  });
```

- [ ] **Step 3: Modify `src/channels/zalo.py` to map new fields**

Open `src/channels/zalo.py`. Find the existing block (around line 139):

```python
        attachments: list[Attachment] = []
        for a in (ev.get("attachments") or []):
            attachments.append(Attachment(
                kind=a.get("kind", "file"),
                url=a.get("href", "") or "",
            ))
```

Replace with:

```python
        attachments: list[Attachment] = []
        for a in (ev.get("attachments") or []):
            if a.get("error"):
                attachments.append(Attachment(
                    kind=a.get("kind", "file"),
                    url="",
                    mime_type=a.get("mime", ""),
                    filename=a.get("filename", ""),
                ))
            else:
                attachments.append(Attachment(
                    kind=a.get("kind", "file"),
                    url=a.get("local_path", "") or "",
                    mime_type=a.get("mime", ""),
                    filename=a.get("filename", ""),
                    size_bytes=int(a.get("size_bytes", 0) or 0),
                ))
```

- [ ] **Step 4: Smoke-import + JS syntax check**

```
python -c "from src.channels.zalo import ZaloMessenger; print('ok')"
node --check src/channels/zalo_bridge/bridge.js && echo "bridge.js syntax ok"
```

Expected: both `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/channels/zalo_bridge/bridge.js src/channels/zalo_bridge/package.json \
        src/channels/zalo_bridge/package-lock.json src/channels/zalo.py
git commit -m "feat(zalo): bridge.js downloads attachments with session cookies

Attachments arrive with local_path, mime, filename, size_bytes (or error
on failure). zalo.py builds Attachment with full fields. Mime inferred
from extension; image fallback to image/jpeg.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: CLI test harness `--attach` flag

**Files:**
- Modify: `scripts/cli_test.py`

- [ ] **Step 1: Add `--attach` argument + mapping to Attachment**

Open `scripts/cli_test.py`. In `main()` add to the `argparse` setup:

```python
    parser.add_argument(
        "--attach", action="append", default=[],
        help="Local file path to attach to the next prompt (repeat for multi)",
    )
```

Above the imports inside the loop, add:

```python
import mimetypes
from src.channels.base import Attachment
```

Inside the input loop, when building `IncomingMessage`, prepare attachments before `mark_start`:

```python
        attachments: list = []
        for ap in (args.attach or []):
            ap_path = os.path.abspath(ap)
            if not os.path.exists(ap_path):
                print(f"\033[31m[skip] not found: {ap}\033[0m")
                continue
            mime, _ = mimetypes.guess_type(ap_path)
            attachments.append(Attachment(
                kind="file",
                url=ap_path,
                mime_type=mime or "application/octet-stream",
                filename=os.path.basename(ap_path),
                size_bytes=os.path.getsize(ap_path),
            ))
        # Once-only: clear after first iteration so subsequent prompts don't reattach
        args.attach = []

        incoming = IncomingMessage(
            channel="cli",
            chat_id=conv_id,
            chat_type="dm",
            sender_id=boss_id,
            sender_name=boss_name,
            text=text,
            attachments=attachments,
            timestamp=int(time.time()),
        )
```

Add `import os` to the top imports if missing.

- [ ] **Step 2: Smoke-test it**

```
python scripts/cli_test.py --help
```

Expected: shows `--attach` in the help.

- [ ] **Step 3: Commit**

```bash
git add scripts/cli_test.py
git commit -m "feat(cli_test): --attach flag for local file ingestion testing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Dockerfile — ensure inbound dir

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Add `mkdir`**

Open `Dockerfile`. Find the section that copies application code (`COPY src ./src` or similar). Right after, add:

```dockerfile
RUN mkdir -p data/inbound
```

(`data/` is mounted as a volume in compose, but the directory must exist at startup so first download doesn't fail.)

- [ ] **Step 2: Build verifies**

```
docker compose build app
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore(docker): ensure data/inbound dir exists in image

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: End-to-end smoke (manual)

After Tasks 1-10 are merged, run this checklist against a staging Zalo + Telegram. Mark each ✓ in the PR description.

- [ ] **Smoke 1 — Zalo PDF DM**: Log in as boss on Zalo, send a 5-page PDF with caption "tóm tắt giúp". Bot replies with summary.
- [ ] **Smoke 2 — Zalo PDF follow-up**: Reply "phần thanh toán nói gì?" within 5 messages. Bot still references the file.
- [ ] **Smoke 3 — Window expiry**: Send 16 unrelated text messages, then ask about the file again. Bot should NOT reference the PDF (sentinel rolled out of recent_messages window).
- [ ] **Smoke 4 — Telegram PDF**: Repeat 1-2 on Telegram.
- [ ] **Smoke 5 — Image (Zalo)**: Send a photo of a menu, ask "món nào rẻ nhất?". Bot reads and answers.
- [ ] **Smoke 6 — DOCX**: Send a 3-page DOCX, ask "tóm tắt 3 ý chính". Bot answers from extracted markdown.
- [ ] **Smoke 7 — Long DOCX**: Send a 50-page DOCX. Bot acknowledges "chỉ đọc 10 trang đầu".
- [ ] **Smoke 8 — Unsupported**: Send a `.xlsx`. Bot replies "chưa hỗ trợ Excel" politely.
- [ ] **Smoke 9 — Encrypted PDF**: Send a password-protected PDF. Bot says "file có password".
- [ ] **Smoke 10 — Multi-file**: Send 2 PDFs in one Zalo message. Bot reads both.
- [ ] **Smoke 11 — CLI parity**: `python scripts/cli_test.py --boss "<name>" --attach data/sample.pdf` and ask a question. Same behaviour.
- [ ] **Smoke 12 — Regression text-only**: Send a normal text question (no file). Flow identical to before.
- [ ] **Smoke 13 — Tool calling**: With a file in context, ask "ghi note nội dung này giúp anh". `add_note` tool fires, note created.

---

## Self-Review Notes (for plan author)

| Spec section | Covered by |
|---|---|
| Sentinel format + parse/strip | Task 1 |
| OpenAI Files API wrapper, retry, expires_after | Task 2 |
| Deps `mammoth`, `pypdf` | Task 3 |
| `file_ingestion.ingest()` dispatch | Task 4 |
| Image cap, PDF cap (size + 20 pages), DOCX cap (size + 20KB), encrypted | Task 4 |
| Concurrent attachments | Task 4 |
| Filename sanitize | Task 4 + Task 7 + Task 8 |
| Opportunistic 24h sweep | Task 4 |
| OpenAI provider sentinel → content parts | Task 5 |
| Local-image-missing fallback | Task 5 |
| `secretary_agent` ingest call + RAG/index strip | Task 6 |
| Router pass-through | Task 6 |
| Telegram download | Task 7 |
| Zalo bridge.js download + zalo.py mapping | Task 8 |
| CLI `--attach` | Task 9 |
| Dockerfile inbound dir | Task 10 |
| Manual smoke (Zalo + Telegram + CLI) | Task 11 |

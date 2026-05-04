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

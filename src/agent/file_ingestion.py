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
from PIL import Image
from pillow_heif import register_heif_opener

from src.channels.base import Attachment
from src.infrastructure import openai_files

# Make Pillow accept .heic/.heif (iPhone photos via Zalo).
register_heif_opener()

logger = logging.getLogger("file_ingestion")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"

# Last-line-of-defense: if a channel sets mime to application/octet-stream
# (or empty) on a recognizable extension, recover it here. Especially helps
# iOS images shipped through Zalo without proper mime.
_EXT_TO_MIME = {
    "pdf": PDF_MIME,
    "docx": DOCX_MIME,
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp", "gif": "image/gif",
    "heic": "image/heic", "heif": "image/heif",
}


def _sniff_mime_from_bytes(path: str) -> str | None:
    """Last resort when channel gave us application/octet-stream + no
    extension (Zalo on iPhone is famous for this). Read the first bytes
    and recognize a few well-known formats."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"GIF8":
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"%PDF":
        return PDF_MIME
    # ISO-BMFF: bytes 4..8 == 'ftyp', then a 4-char major brand
    if head[4:8] == b"ftyp" and head[8:12] in (
        b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1",
    ):
        return "image/heic"
    return None

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
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    # Channels occasionally hand us octet-stream / empty mime on files that
    # are actually well-known formats (iOS photos via Zalo, etc.). Try ext
    # then magic bytes before deciding "unsupported".
    if mime in ("", "application/octet-stream"):
        if ext in _EXT_TO_MIME:
            mime = _EXT_TO_MIME[ext]
        elif a.url:
            sniffed = _sniff_mime_from_bytes(a.url)
            if sniffed:
                mime = sniffed
                logger.info("ingest sniff: %r → %s (no ext)", name, mime)

    logger.info(
        "ingest one: filename=%r mime=%s size=%d url=%s",
        name, mime, a.size_bytes, a.url[:80],
    )

    if not a.url:
        return f"[Tệp {name} — không tải được]"
    if mime.startswith("image/"):
        # OpenAI Vision only accepts JPEG/PNG/WEBP/GIF. iPhone photos sent
        # via Zalo arrive as HEIC/HEIF — convert to JPEG transparently.
        if mime in ("image/heic", "image/heif"):
            try:
                new_path = await asyncio.to_thread(_convert_heic_to_jpeg, a.url)
            except Exception as e:
                logger.warning("HEIC convert failed for %s: %s", a.url, e)
                return f"[Tệp {name} — không decode được ảnh iPhone]"
            return f"[LOCAL_IMAGE: path={new_path} mime=image/jpeg]"
        # Pass the resolved mime explicitly — sniffed mimes never reach
        # back into a.mime_type, so _ingest_image must not read that field.
        return _ingest_image(a, name, mime)
    if mime == PDF_MIME:
        return await _ingest_pdf(client, a, name, mime)
    if mime == DOCX_MIME:
        return await _ingest_docx(a, name)
    ext_label = ext or "?"
    return f"[Tệp {name} — chưa hỗ trợ định dạng .{ext_label}]"


def _ingest_image(a: Attachment, name: str, mime: str) -> str:
    if a.size_bytes > _MAX_IMAGE_BYTES:
        return f"[Tệp {name} — ảnh quá to (>20MB)]"
    return f"[LOCAL_IMAGE: path={a.url} mime={mime}]"


async def _ingest_pdf(client: Any, a: Attachment, name: str, mime: str) -> str:
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
        file_id = await openai_files.upload(client, a.url, mime, name)
    except Exception as e:
        logger.warning("openai_files.upload %s failed: %s", name, e)
        return f"[Tệp {name} — tạm thời lỗi, gửi lại giúp anh]"
    _try_delete(a.url)
    return f"[OPENAI_FILE: file_id={file_id} mime={mime} filename={name}]"


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


def _convert_heic_to_jpeg(path: str) -> str:
    """Re-encode HEIC/HEIF → JPEG next to the original. Returns new path."""
    new_path = path.rsplit(".", 1)[0] + ".jpg"
    if path == new_path:
        new_path = path + ".jpg"
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(new_path, "JPEG", quality=85)
    return new_path


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

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
    p.write_bytes(b"PK")
    big_md = "x" * (25 * 1024)
    with patch("src.agent.file_ingestion._mammoth_convert", return_value=big_md):
        out = await file_ingestion.ingest(
            object(), [_att(str(p), file_ingestion.DOCX_MIME, "doc.docx", size=2)], "conv-1",
        )
    assert out.startswith("[Tệp doc.docx]\n")
    body = out.split("\n", 1)[1]
    assert len(body) <= 20 * 1024 + 100
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
    assert old.exists() and fresh.exists()
    img = base / "img.jpg"
    img.write_bytes(b"\xff")
    att = _att(str(img), "image/jpeg", "img.jpg", size=1)
    await file_ingestion.ingest(object(), [att], "conv-1")
    assert not old.exists(), "24h-old file should be swept"
    assert fresh.exists(), "recent file kept"

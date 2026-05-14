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

import pytest

import src.media.adapters.web as web
from src.media.adapters.web import WebExtractor


@pytest.mark.asyncio
async def test_youtube_uses_transcript(monkeypatch):
    monkeypatch.setattr(web, "_yt_transcript", lambda vid: "xin chào phần hai")
    monkeypatch.setattr(web, "_yt_meta", lambda url: ("Tiêu đề video", "vid12345678", "desc"))
    res = await WebExtractor().extract(url="https://youtu.be/vid12345678")
    assert "xin chào phần hai" in res.media_text
    assert res.title == "Tiêu đề video"


@pytest.mark.asyncio
async def test_youtube_falls_back_to_description(monkeypatch):
    monkeypatch.setattr(web, "_yt_transcript", lambda vid: "")  # no transcript
    monkeypatch.setattr(web, "_yt_meta", lambda url: ("T", "vid12345678", "mô tả dự phòng"))
    res = await WebExtractor().extract(url="https://www.youtube.com/watch?v=vid12345678")
    assert "mô tả dự phòng" in res.media_text


@pytest.mark.asyncio
async def test_tiktok_best_effort(monkeypatch):
    monkeypatch.setattr(web, "_yt_meta", lambda url: ("TT title", "ttid", "mô tả tiktok"))
    res = await WebExtractor().extract(url="https://www.tiktok.com/@x/video/123")
    assert "mô tả tiktok" in res.media_text
    assert res.title == "TT title"

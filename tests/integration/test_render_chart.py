"""render_chart tool: validate spec + chỉ chạy trên kênh web (chart trong chat
web boss — user chốt 2026-07-03; kênh khác trả lời chữ)."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from src.tools.core.charts import render_chart


def _ctx(provider="web"):
    return SimpleNamespace(provider=provider)


@pytest.mark.asyncio
async def test_returns_embed_with_valid_spec():
    out = await render_chart(
        _ctx(), type="bar", title="Việc mở theo người",
        labels=["An", "Bình"], series=[{"name": "mở", "data": [3, 2]}],
    )
    assert out.error is None
    m = re.search(r"```chart\n([\s\S]*?)\n```", out.content["embed"])
    spec = json.loads(m.group(1))
    assert spec == {
        "type": "bar", "title": "Việc mở theo người",
        "labels": ["An", "Bình"], "series": [{"name": "mở", "data": [3.0, 2.0]}],
    }


@pytest.mark.asyncio
async def test_rejects_non_web_channel():
    out = await render_chart(
        _ctx(provider="zalo"), type="bar", labels=["A"], series=[{"data": [1]}])
    assert out.error is not None and "chữ" in out.error


@pytest.mark.asyncio
async def test_rejects_mismatched_lengths_and_empty():
    out = await render_chart(
        _ctx(), type="pie", labels=["A", "B"], series=[{"data": [1]}])
    assert out.error is not None and "khớp" in out.error
    out = await render_chart(_ctx(), type="line", labels=[], series=[{"data": []}])
    assert out.error is not None


@pytest.mark.asyncio
async def test_caps_points_and_series():
    out = await render_chart(
        _ctx(), type="bar",
        labels=[f"n{i}" for i in range(50)],
        series=[{"data": list(range(50))}] * 5,
    )
    spec = json.loads(re.search(r"```chart\n([\s\S]*?)\n```", out.content["embed"]).group(1))
    assert len(spec["labels"]) == 30
    assert len(spec["series"]) == 3
    assert len(spec["series"][0]["data"]) == 30

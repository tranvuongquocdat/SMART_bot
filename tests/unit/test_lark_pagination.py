"""search_records must paginate using page_token until has_more=false."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.infrastructure.lark_client as lark


def _resp(items, has_more=False, page_token=None):
    body = {
        "code": 0,
        "data": {
            "items": [{"record_id": rid, "fields": fields} for rid, fields in items],
            "has_more": has_more,
            "page_token": page_token,
        },
    }
    r = MagicMock()
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


async def test_search_records_returns_all_pages():
    page1 = _resp([("r1", {"a": 1}), ("r2", {"a": 2})], has_more=True, page_token="p2")
    page2 = _resp([("r3", {"a": 3})], has_more=False)

    client = MagicMock()
    client.get = AsyncMock(side_effect=[page1, page2])
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"):
        rows = await lark.search_records("base", "tbl")

    assert [r["record_id"] for r in rows] == ["r1", "r2", "r3"]
    assert client.get.call_count == 2
    second_call_params = client.get.call_args_list[1].kwargs["params"]
    assert second_call_params.get("page_token") == "p2"


async def test_search_records_stops_on_hard_cap(caplog):
    pages = [
        _resp([(f"r{p}-{i}", {}) for i in range(500)], has_more=True, page_token=f"p{p+1}")
        for p in range(11)
    ]
    client = MagicMock()
    client.get = AsyncMock(side_effect=pages)
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"), \
         caplog.at_level("WARNING"):
        rows = await lark.search_records("base", "tbl")

    assert len(rows) == 5000
    assert any("hard cap" in rec.message.lower() for rec in caplog.records)


async def test_search_records_single_page_no_token():
    page = _resp([("r1", {"x": 1})], has_more=False)
    client = MagicMock()
    client.get = AsyncMock(return_value=page)
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"):
        rows = await lark.search_records("base", "tbl")

    assert rows == [{"record_id": "r1", "x": 1}]
    assert client.get.call_count == 1
    first_params = client.get.call_args.kwargs["params"]
    assert "page_token" not in first_params

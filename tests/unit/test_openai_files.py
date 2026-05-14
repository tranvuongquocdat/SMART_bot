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
    assert kwargs["extra_body"] == {
        "expires_after": {"anchor": "created_at", "seconds": 30 * 24 * 3600},
    }


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
    await openai_files.delete(client, "file-x")
    client.files.delete.assert_awaited_once_with("file-x")

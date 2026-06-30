"""Proxy pool — IP dân cư gán theo từng boss.

Một boss được gán tối đa một proxy; mọi bot account session-based của boss đó
(zalo, messenger sau này) cùng ra internet qua proxy này → các kênh của một
khách trông như thiết bị của cùng một người. Telegram/web không dùng proxy.

URL proxy chứa credentials (scheme://user:pass@host:port) nên mã hóa Fernet
trước khi lưu, không bao giờ trả raw ra API.
"""

from __future__ import annotations

import logging
from typing import Any

from cryptography.fernet import Fernet

from src.config import settings

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode())


def encrypt_url(url: str) -> bytes:
    return _fernet().encrypt(url.encode())


def decrypt_url(blob: bytes | None) -> str | None:
    if not blob:
        return None
    try:
        return _fernet().decrypt(bytes(blob)).decode()
    except Exception:
        return None


def mask_url(url: str | None) -> str | None:
    """scheme://user:***@host:port — che password để hiển thị an toàn."""
    if not url:
        return None
    try:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            auth, hostport = rest.rsplit("@", 1)
            user = auth.split(":", 1)[0]
            return f"{scheme}://{user}:***@{hostport}"
        return url
    except Exception:
        return "***"


class ProxyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


async def resolve_for_boss(pool: Any, boss_id: int) -> str | None:
    """URL proxy của boss (đã giải mã) nếu có và đang active; None nếu không."""
    async with pool.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT p.url_enc, p.status
            FROM users u JOIN proxies p ON p.id = u.proxy_id
            WHERE u.id = $1
            """,
            boss_id,
        )
    if not row or row["status"] != "active":
        return None
    return decrypt_url(row["url_enc"])


async def list_proxies(pool: Any) -> list[dict]:
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM users u WHERE u.proxy_id = p.id) AS assigned_count
            FROM proxies p
            ORDER BY p.created_at DESC
            """
        )
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "url_masked": mask_url(decrypt_url(r["url_enc"])),
            "region": r["region"],
            "status": r["status"],
            "max_bosses": r["max_bosses"],
            "assigned_count": int(r["assigned_count"]),
            "notes": r["notes"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def create_proxy(
    pool: Any, label: str, url: str, region: str | None, max_bosses: int, notes: str | None
) -> int:
    url = (url or "").strip()
    if "://" not in url:
        raise ProxyError(422, "Proxy URL must include a scheme (http://, https://, socks5://)")
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO proxies (label, url_enc, region, max_bosses, notes)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
            """,
            label.strip() or "proxy",
            encrypt_url(url),
            (region or "").strip() or None,
            max(1, int(max_bosses)),
            notes,
        )


async def update_proxy(pool: Any, proxy_id: int, fields: dict) -> None:
    sets: list[str] = []
    vals: list[Any] = [proxy_id]  # heterogeneous SQL params (int/str/encrypted bytes)
    i = 2
    for key in ("label", "region", "status", "max_bosses", "notes"):
        if key in fields and fields[key] is not None:
            sets.append(f"{key}=${i}")
            vals.append(int(fields[key]) if key == "max_bosses" else fields[key])
            i += 1
    if "url" in fields and fields["url"]:
        url = fields["url"].strip()
        if "://" not in url:
            raise ProxyError(422, "Proxy URL must include a scheme")
        sets.append(f"url_enc=${i}")
        vals.append(encrypt_url(url))
        i += 1
    if not sets:
        return
    sets.append("updated_at=NOW()")
    async with pool.acquire() as c:
        await c.execute(f"UPDATE proxies SET {', '.join(sets)} WHERE id=$1", *vals)


async def delete_proxy(pool: Any, proxy_id: int) -> None:
    async with pool.acquire() as c:
        n = await c.fetchval(
            "SELECT COUNT(*) FROM users WHERE proxy_id=$1", proxy_id
        )
        if n:
            raise ProxyError(409, f"Assigned to {n} customer(s) — unassign before deleting")
        await c.execute("DELETE FROM proxies WHERE id=$1", proxy_id)


async def assign_to_boss(pool: Any, boss_id: int, proxy_id: int | None) -> None:
    """Gán proxy cho boss (None = gỡ). Enforce cap max_bosses."""
    async with pool.acquire() as c:
        if proxy_id is not None:
            p = await c.fetchrow(
                "SELECT max_bosses, status FROM proxies WHERE id=$1", proxy_id
            )
            if not p:
                raise ProxyError(404, "proxy does not exist")
            if p["status"] != "active":
                raise ProxyError(409, "proxy is not active")
            used = await c.fetchval(
                "SELECT COUNT(*) FROM users WHERE proxy_id=$1 AND id<>$2",
                proxy_id,
                boss_id,
            )
            if used >= p["max_bosses"]:
                raise ProxyError(
                    409, f"Proxy reached its cap of {p['max_bosses']} customers"
                )
        await c.execute(
            "UPDATE users SET proxy_id=$2 WHERE id=$1", boss_id, proxy_id
        )


async def test_proxy(url: str, timeout_s: float = 12.0) -> dict:
    """Gọi 1 request qua proxy lấy IP công khai. {ok, ip?, message?}."""
    import httpx

    try:
        async with httpx.AsyncClient(proxy=url, timeout=timeout_s) as client:
            r = await client.get("https://api.ipify.org?format=json")
        if r.status_code == 200:
            return {"ok": True, "ip": r.json().get("ip")}
        return {"ok": False, "message": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}

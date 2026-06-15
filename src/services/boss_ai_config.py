"""Cấu hình AI của một boss — logic dùng chung cho 2 đường:

  - Boss tự chỉnh trong Cài đặt > AI (``api_admin``)
  - Superadmin chỉnh hộ trong drawer Boss (``api_superadmin_bosses``)

Mọi hàm nhận ``boss_id`` là boss ĐÍCH (không phải actor). Caller chịu trách
nhiệm authz; hàm chỉ enforce bất biến dữ liệu (model phải thuộc nền tảng hoặc
chính boss đó, model riêng bắt buộc có BYO key của provider...).

Lỗi nghiệp vụ raise ``AiConfigError(status, message)`` — endpoint map sang
HTTPException.
"""

from __future__ import annotations

import json
import logging

import httpx
from cryptography.fernet import Fernet

from src.config import settings

log = logging.getLogger(__name__)

PROVIDERS = ("openai", "groq", "gemini")

# endpoint_kind + base_url mặc định khi boss/superadmin thêm model theo provider
PROVIDER_DEFAULTS = {
    "openai": ("openai_compat", None),
    "groq": ("openai_compat", "https://api.groq.com/openai/v1"),
    "gemini": ("gemini", None),
}

# Provider tuỳ chỉnh / self-hosted (vLLM, Ollama, OpenRouter, ...) — luôn nói
# OpenAI-compatible; base_url do boss/superadmin nhập, lưu ở users.ai_provider_urls.
CUSTOM_ENDPOINT_KIND = "openai_compat"


def _norm_provider(p: str) -> str:
    return (p or "").strip().lower()


def _is_builtin(provider: str) -> bool:
    return provider in PROVIDER_DEFAULTS


# Khả năng (capabilities) hợp lệ cho model. 'text' ngầm định nhưng vẫn cho chọn.
ALLOWED_CAPS = ("text", "vision", "thinking", "tools", "audio")


def _norm_caps(raw) -> list[str]:
    """Chuẩn hoá list capability về tập hợp lệ, giữ thứ tự ALLOWED_CAPS, không trùng."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    items = {str(x).strip().lower() for x in (raw or [])}
    return [c for c in ALLOWED_CAPS if c in items]


def _parse_cost(raw) -> float | None:
    """Giá $/1M token tự nhập → float ≥ 0, hoặc None nếu trống/không hợp lệ."""
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def _parse_urls(raw) -> dict:
    """ai_provider_urls (JSONB) → dict. asyncpg trả JSONB dạng str (no codec)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return dict(raw or {})


async def resolve_provider_url(pool, boss_id: int, provider: str) -> str | None:
    """base_url của provider: built-in → default; custom → giá trị boss đã lưu."""
    if _is_builtin(provider):
        return PROVIDER_DEFAULTS[provider][1]
    async with pool.acquire() as c:
        raw = await c.fetchval(
            "SELECT ai_provider_urls FROM users WHERE id=$1", boss_id
        )
    return _parse_urls(raw).get(provider)


SLOT_COLUMNS = {
    "smart": "smart_model_id",
    "fast": "fast_model_id",
    "vision": "vision_model_id",
}


class AiConfigError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode())


def _decrypt_keys(blob: bytes | None) -> dict[str, str]:
    if not blob:
        return {}
    try:
        return json.loads(_fernet().decrypt(bytes(blob)).decode())
    except Exception:
        return {}


def mask_keys(blob: bytes | None) -> dict[str, dict]:
    """{provider: {present, last_4}} — không bao giờ trả raw key."""
    result: dict[str, dict] = {}
    for prov, key_val in _decrypt_keys(blob).items():
        result[prov] = {"present": True, "last_4": key_val[-4:] if len(key_val) >= 4 else ""}
    for prov in PROVIDERS:
        result.setdefault(prov, {"present": False})
    return result


# ---------------------------------------------------------------------------
# Đọc cấu hình
# ---------------------------------------------------------------------------


async def get_ai_settings(pool, boss_id: int) -> dict:
    """Slots + models khả dụng (nền tảng + của boss) + keys masked + cost cap."""
    async with pool.acquire() as c:
        boss = await c.fetchrow(
            """
            SELECT smart_model_id, fast_model_id, vision_model_id,
                   cost_cap_usd_daily, api_keys_enc, ai_provider_urls
            FROM users WHERE id = $1
            """,
            boss_id,
        )
        if not boss:
            raise AiConfigError(404, "boss not found")
        models = await c.fetch(
            """
            SELECT id, name, provider, tier, capabilities, ctx_max,
                   cost_per_1m_input_usd, cost_per_1m_output_usd, is_platform_default,
                   owner_boss_id
            FROM models
            WHERE is_active = TRUE AND (owner_boss_id IS NULL OR owner_boss_id = $1)
            ORDER BY owner_boss_id NULLS FIRST, tier, provider, name
            """,
            boss_id,
        )

    def _caps(raw) -> list[str]:
        # asyncpg trả JSONB dạng chuỗi — list('["vision"]') sẽ tách thành ký tự
        # khiến dropdown Vision không bao giờ match model nào.
        if not raw:
            return []
        if isinstance(raw, str):
            try:
                return list(json.loads(raw))
            except Exception:
                return []
        return list(raw)

    return {
        "slots": [
            {"slot": slot, "model_id": boss[col]} for slot, col in SLOT_COLUMNS.items()
        ],
        "keys": mask_keys(boss["api_keys_enc"]),
        "provider_urls": _parse_urls(boss["ai_provider_urls"]),
        "models": [
            {
                "id": int(m["id"]),
                "name": m["name"],
                "provider": m["provider"],
                "tier": m["tier"],
                "capabilities": _caps(m["capabilities"]),
                "ctx_max": int(m["ctx_max"] or 0),
                "cost_per_1m_input_usd": float(m["cost_per_1m_input_usd"] or 0),
                "cost_per_1m_output_usd": float(m["cost_per_1m_output_usd"] or 0),
                "is_platform_default": bool(m["is_platform_default"]),
                "is_own": m["owner_boss_id"] is not None,
            }
            for m in models
        ],
        "cost_cap_usd_daily": float(boss["cost_cap_usd_daily"] or 0),
    }


# ---------------------------------------------------------------------------
# Slots + cost cap
# ---------------------------------------------------------------------------


async def set_model_slot(pool, boss_id: int, slot: str, model_id: int | None) -> None:
    col = SLOT_COLUMNS.get(slot)
    if col is None:
        raise AiConfigError(422, "invalid slot")
    async with pool.acquire() as c:
        if model_id is not None:
            allowed = await c.fetchval(
                """
                SELECT 1 FROM models
                WHERE id=$1 AND is_active=TRUE
                  AND (owner_boss_id IS NULL OR owner_boss_id=$2)
                """,
                int(model_id),
                boss_id,
            )
            if not allowed:
                raise AiConfigError(404, "model not found")
        await c.execute(
            f"UPDATE users SET {col}=$2 WHERE id=$1",
            boss_id,
            int(model_id) if model_id is not None else None,
        )


async def set_cost_cap(pool, boss_id: int, cap: float) -> None:
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE users SET cost_cap_usd_daily=$2 WHERE id=$1", boss_id, float(cap)
        )


# ---------------------------------------------------------------------------
# BYO keys
# ---------------------------------------------------------------------------


async def test_provider_key(
    provider: str, api_key: str, base_url: str | None = None
) -> tuple[bool, str]:
    """Gọi 1 request nhẹ kiểm tra key sống. Trả (ok, message).

    Custom/self-hosted (có base_url): gọi ``{base_url}/models`` kiểu OpenAI.
    """
    provider = _norm_provider(provider)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "openai":
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "groq":
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "gemini":
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key},
                )
            elif base_url:
                r = await client.get(
                    f"{base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            else:
                return False, "Invalid provider"
    except httpx.RequestError:
        return False, "Could not reach provider"
    if r.status_code == 200:
        return True, "Key is valid"
    if r.status_code in (401, 403):
        return False, "Invalid or expired key"
    return False, f"Provider returned {r.status_code}"


async def set_api_key(
    pool,
    boss_id: int,
    provider: str,
    api_key: str,
    validate: bool = False,
    base_url: str | None = None,
) -> None:
    provider = _norm_provider(provider)
    if not provider:
        raise AiConfigError(422, "unknown provider")
    base_url = (base_url or "").strip().rstrip("/") or None
    is_custom = not _is_builtin(provider)
    if is_custom and not base_url:
        raise AiConfigError(422, "Custom provider cần base_url")
    api_key = api_key.strip()
    if not api_key:
        raise AiConfigError(422, "api_key required")
    if validate:
        ok, message = await test_provider_key(provider, api_key, base_url=base_url)
        if not ok:
            raise AiConfigError(422, message)

    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT api_keys_enc, ai_provider_urls FROM users WHERE id=$1", boss_id
        )
        keys = _decrypt_keys(row["api_keys_enc"])
        keys[provider] = api_key
        urls = _parse_urls(row["ai_provider_urls"])
        if is_custom:
            urls[provider] = base_url
        await c.execute(
            "UPDATE users SET api_keys_enc=$2, ai_provider_urls=$3::jsonb WHERE id=$1",
            boss_id,
            _fernet().encrypt(json.dumps(keys).encode()),
            json.dumps(urls),
        )


async def clear_api_key(pool, boss_id: int, provider: str) -> None:
    provider = _norm_provider(provider)
    if not provider:
        raise AiConfigError(422, "unknown provider")
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT api_keys_enc, ai_provider_urls FROM users WHERE id=$1", boss_id
        )
        keys = _decrypt_keys(row["api_keys_enc"])
        keys.pop(provider, None)
        urls = _parse_urls(row["ai_provider_urls"])
        urls.pop(provider, None)
        await c.execute(
            "UPDATE users SET api_keys_enc=$2, ai_provider_urls=$3::jsonb WHERE id=$1",
            boss_id,
            _fernet().encrypt(json.dumps(keys).encode()),
            json.dumps(urls),
        )


async def boss_has_key(pool, boss_id: int, provider: str) -> bool:
    async with pool.acquire() as c:
        blob = await c.fetchval("SELECT api_keys_enc FROM users WHERE id=$1", boss_id)
    return bool(_decrypt_keys(blob).get(provider))


async def resolve_key(pool, boss_id: int, provider: str) -> str | None:
    """Key BYO của boss; fallback key nền tảng (chỉ dùng duyệt danh sách model)."""
    async with pool.acquire() as c:
        blob = await c.fetchval("SELECT api_keys_enc FROM users WHERE id=$1", boss_id)
    keys = _decrypt_keys(blob)
    if keys.get(provider):
        return keys[provider]
    return {
        "openai": settings.PLATFORM_OPENAI_API_KEY,
        "groq": settings.PLATFORM_GROQ_API_KEY,
    }.get(provider) or None


# ---------------------------------------------------------------------------
# Model riêng của boss (BYO)
# ---------------------------------------------------------------------------


async def create_own_model(pool, ctx, boss_id: int, payload: dict) -> int:
    """ctx: BossContext của actor (boss tự thêm hoặc superadmin thêm hộ)."""
    import asyncpg

    from src.repositories.models import ModelsRepo

    provider = _norm_provider(payload.get("provider"))
    name = (payload.get("name") or "").strip()
    tier = (payload.get("tier") or "smart").strip().lower()

    is_custom = not _is_builtin(provider)
    custom_url = None
    if is_custom:
        custom_url = await resolve_provider_url(pool, boss_id, provider)
        if not custom_url:
            raise AiConfigError(422, "unknown provider")
    if not name or len(name) > 200:
        raise AiConfigError(422, "invalid model name")
    if tier not in SLOT_COLUMNS:
        raise AiConfigError(422, "invalid tier")
    if not await boss_has_key(pool, boss_id, provider):
        raise AiConfigError(
            409, f"Save the boss's {provider} API key before adding a custom model"
        )

    if is_custom:
        endpoint_kind, base_url = CUSTOM_ENDPOINT_KIND, custom_url
    else:
        endpoint_kind, base_url = PROVIDER_DEFAULTS[provider]
    # capabilities: ưu tiên list FE gửi; fallback cờ vision (tương thích cũ).
    if payload.get("capabilities") is not None:
        capabilities = _norm_caps(payload.get("capabilities"))
    else:
        capabilities = ["vision"] if (tier == "vision" or payload.get("vision")) else []

    # Giá tự nhập ($/1M token) — để usage tính được chi phí cho model BYO/không
    # tra được giá. Bỏ trống = None (usage hiển thị "chưa tính được giá").
    cost_in = _parse_cost(payload.get("cost_per_1m_input_usd"))
    cost_out = _parse_cost(payload.get("cost_per_1m_output_usd"))

    repo = ModelsRepo(pool, ctx)
    try:
        return await repo.insert(
            name=name,
            provider=provider,
            endpoint_kind=endpoint_kind,
            base_url=base_url,
            tier=tier,
            ctx_max=int(payload.get("ctx_max") or 128_000),
            capabilities=capabilities,
            cost_in=cost_in,
            cost_out=cost_out,
            notes="BYO",
            owner_boss_id=boss_id,
        )
    except asyncpg.UniqueViolationError:
        raise AiConfigError(409, "This model is already in the boss's list")


async def patch_own_model(pool, boss_id: int, model_id: int, payload: dict) -> None:
    """Sửa thông số model riêng của boss (tier, capabilities, cost, ctx_max).

    Provider/name/endpoint cố định khi tạo — chỉ chỉnh các thông số 'mềm'.
    """
    async with pool.acquire() as c:
        owned = await c.fetchval(
            "SELECT 1 FROM models WHERE id=$1 AND owner_boss_id=$2", model_id, boss_id
        )
        if not owned:
            raise AiConfigError(404, "model not found")

        sets: list[str] = []
        vals: list = []
        i = 1
        if payload.get("tier"):
            tier = str(payload["tier"]).strip().lower()
            if tier not in SLOT_COLUMNS:
                raise AiConfigError(422, "invalid tier")
            sets.append(f"tier=${i}")
            vals.append(tier)
            i += 1
        if "capabilities" in payload:
            sets.append(f"capabilities=${i}::jsonb")
            vals.append(json.dumps(_norm_caps(payload.get("capabilities"))))
            i += 1
        if "cost_per_1m_input_usd" in payload:
            sets.append(f"cost_per_1m_input_usd=${i}")
            vals.append(_parse_cost(payload.get("cost_per_1m_input_usd")))
            i += 1
        if "cost_per_1m_output_usd" in payload:
            sets.append(f"cost_per_1m_output_usd=${i}")
            vals.append(_parse_cost(payload.get("cost_per_1m_output_usd")))
            i += 1
        if payload.get("ctx_max"):
            sets.append(f"ctx_max=${i}")
            vals.append(int(payload["ctx_max"]))
            i += 1
        if not sets:
            return
        vals.append(model_id)
        await c.execute(
            f"UPDATE models SET {', '.join(sets)} WHERE id=${i}", *vals
        )


async def delete_own_model(pool, boss_id: int, model_id: int) -> None:
    async with pool.acquire() as c:
        owned = await c.fetchval(
            "SELECT 1 FROM models WHERE id=$1 AND owner_boss_id=$2",
            model_id,
            boss_id,
        )
        if not owned:
            raise AiConfigError(404, "model not found")
        # Gỡ model khỏi slot trước khi xoá để không vỡ routing.
        await c.execute(
            """
            UPDATE users SET
              smart_model_id  = CASE WHEN smart_model_id=$2 THEN NULL ELSE smart_model_id END,
              fast_model_id   = CASE WHEN fast_model_id=$2 THEN NULL ELSE fast_model_id END,
              vision_model_id = CASE WHEN vision_model_id=$2 THEN NULL ELSE vision_model_id END
            WHERE id=$1
            """,
            boss_id,
            model_id,
        )
        await c.execute("DELETE FROM models WHERE id=$1", model_id)


async def list_provider_models(pool, boss_id: int, provider: str) -> dict:
    """Danh sách model trực tiếp từ provider, chạy bằng key của boss.

    Trả {ok, models: [{id}], message?} — không bao giờ lộ key.
    """
    provider = _norm_provider(provider)
    is_custom = not _is_builtin(provider)
    custom_url = None
    if is_custom:
        custom_url = await resolve_provider_url(pool, boss_id, provider)
        if not custom_url:
            return {"ok": False, "models": [], "message": "Invalid provider"}
    key = await resolve_key(pool, boss_id, provider)
    if not key:
        return {"ok": False, "models": [], "message": f"No {provider} API key yet"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "gemini":
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": key, "pageSize": 1000},
                )
            else:
                if is_custom:
                    base = custom_url.rstrip("/")
                elif provider == "openai":
                    base = "https://api.openai.com/v1"
                else:
                    base = "https://api.groq.com/openai/v1"
                r = await client.get(
                    f"{base}/models", headers={"Authorization": f"Bearer {key}"}
                )
    except httpx.RequestError as e:
        log.warning("list_provider_models network err provider=%s: %s", provider, e)
        return {"ok": False, "models": [], "message": "Could not reach provider"}

    if r.status_code != 200:
        return {"ok": False, "models": [], "message": f"Provider returned {r.status_code}"}

    try:
        data = r.json()
        if provider == "gemini":
            ids = [
                m["name"].removeprefix("models/")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        else:
            ids = [m["id"] for m in data.get("data", [])]
    except Exception:
        return {"ok": False, "models": [], "message": "Could not read provider response"}

    return {"ok": True, "models": [{"id": i} for i in sorted(ids)]}

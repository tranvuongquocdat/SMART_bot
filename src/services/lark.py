import time

import httpx

_client: httpx.AsyncClient | None = None
_app_id: str = ""
_app_secret: str = ""
_base_token: str = ""

_tenant_token: str = ""
_token_expires: float = 0

LARK_API = "https://open.larksuite.com/open-apis"


async def init_lark(app_id: str, app_secret: str, base_token: str):
    global _client, _app_id, _app_secret, _base_token
    _app_id = app_id
    _app_secret = app_secret
    _base_token = base_token
    _client = httpx.AsyncClient(timeout=15.0)


async def _get_token() -> str:
    global _tenant_token, _token_expires
    if time.time() < _token_expires:
        return _tenant_token

    resp = await _client.post(
        f"{LARK_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": _app_id, "app_secret": _app_secret},
    )
    resp.raise_for_status()
    data = resp.json()
    _tenant_token = data["tenant_access_token"]
    _token_expires = time.time() + data.get("expire", 7200) - 300
    return _tenant_token


async def _headers() -> dict:
    token = await _get_token()
    return {"Authorization": f"Bearer {token}"}


async def create_record(table_id: str, fields: dict) -> dict:
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps/{_base_token}/tables/{table_id}/records",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["record"]


async def search_records(table_id: str, filter_expr: str = "") -> list[dict]:
    params = {"page_size": 100}
    if filter_expr:
        params["filter"] = filter_expr
    resp = await _client.get(
        f"{LARK_API}/bitable/v1/apps/{_base_token}/tables/{table_id}/records",
        headers=await _headers(),
        params=params,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    items = data.get("items", [])
    return [{"record_id": r["record_id"], **r["fields"]} for r in items]


async def update_record(table_id: str, record_id: str, fields: dict) -> dict:
    resp = await _client.put(
        f"{LARK_API}/bitable/v1/apps/{_base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    return resp.json()["data"]["record"]


async def close_lark():
    if _client:
        await _client.aclose()

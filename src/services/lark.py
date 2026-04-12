import time

import httpx

_client: httpx.AsyncClient | None = None
_app_id: str = ""
_app_secret: str = ""

_tenant_token: str = ""
_token_expires: float = 0

LARK_API = "https://open.larksuite.com/open-apis"

# ---------------------------------------------------------------------------
# Field definitions for provisioning
# ---------------------------------------------------------------------------

PEOPLE_FIELDS = [
    {"field_name": "Tên", "type": 1},
    {"field_name": "Tên gọi", "type": 1},
    {"field_name": "Chat ID", "type": 2},
    {"field_name": "Username", "type": 1},
    {"field_name": "Type", "type": 1},
    {"field_name": "Nhóm", "type": 1},
    {"field_name": "Vai trò", "type": 1},
    {"field_name": "Kỹ năng", "type": 1},
    {"field_name": "SĐT", "type": 1},
    {"field_name": "Ghi chú", "type": 1},
]

TASKS_FIELDS = [
    {"field_name": "Tên task", "type": 1},
    {"field_name": "Assignee", "type": 1},
    {"field_name": "Deadline", "type": 5},
    {"field_name": "Start time", "type": 5},
    {"field_name": "Location", "type": 1},
    {"field_name": "Priority", "type": 1},
    {"field_name": "Status", "type": 1},
    {"field_name": "Project", "type": 1},
    {"field_name": "Giao bởi", "type": 1},
    {"field_name": "Tin nhắn gốc", "type": 1},
    {"field_name": "Group ID", "type": 2},
]

PROJECTS_FIELDS = [
    {"field_name": "Tên dự án", "type": 1},
    {"field_name": "Mô tả", "type": 1},
    {"field_name": "Người phụ trách", "type": 1},
    {"field_name": "Thành viên", "type": 1},
    {"field_name": "Deadline", "type": 5},
    {"field_name": "Trạng thái", "type": 1},
]

IDEAS_FIELDS = [
    {"field_name": "Nội dung", "type": 1},
    {"field_name": "Tags", "type": 1},
    {"field_name": "Người tạo", "type": 1},
    {"field_name": "Project", "type": 1},
]

# ---------------------------------------------------------------------------
# Initialisation / teardown
# ---------------------------------------------------------------------------


async def init_lark(app_id: str, app_secret: str):
    global _client, _app_id, _app_secret
    _app_id = app_id
    _app_secret = app_secret
    _client = httpx.AsyncClient(timeout=15.0)


async def close_lark():
    if _client:
        await _client.aclose()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Provisioning helpers
# ---------------------------------------------------------------------------


async def create_base(name: str) -> dict:
    """Create a new Lark Bitable app.

    Returns a dict with keys ``app_token`` and ``default_table_id``.
    """
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps",
        headers=await _headers(),
        json={"name": name},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    app = body["data"]["app"]
    return {
        "app_token": app["app_token"],
        "default_table_id": app.get("default_table_id", ""),
    }


async def create_table(base_token: str, name: str, fields: list[dict]) -> str:
    """Create a table inside a Bitable app.

    Returns the new ``table_id``.
    """
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables",
        headers=await _headers(),
        json={"table": {"name": name, "fields": fields}},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["table_id"]


async def delete_table(base_token: str, table_id: str):
    """Delete a table from a Bitable app (used to remove the default table)."""
    resp = await _client.delete(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}",
        headers=await _headers(),
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")


async def provision_workspace(company_name: str) -> dict:
    """Provision a full Lark Bitable workspace for a new boss/company.

    Steps:
    1. Create a new Bitable app named "{company_name} - AI Secretary".
    2. Create 4 tables: People, Tasks, Projects, Ideas.
    3. Delete the default table auto-created by Lark.

    Returns:
        {
            "base_token": str,
            "table_people": str,
            "table_tasks": str,
            "table_projects": str,
            "table_ideas": str,
        }
    """
    base_info = await create_base(f"{company_name} - AI Secretary")
    base_token = base_info["app_token"]
    default_table_id = base_info["default_table_id"]

    table_people = await create_table(base_token, "People", PEOPLE_FIELDS)
    table_tasks = await create_table(base_token, "Tasks", TASKS_FIELDS)
    table_projects = await create_table(base_token, "Projects", PROJECTS_FIELDS)
    table_ideas = await create_table(base_token, "Ideas", IDEAS_FIELDS)

    if default_table_id:
        await delete_table(base_token, default_table_id)

    return {
        "base_token": base_token,
        "table_people": table_people,
        "table_tasks": table_tasks,
        "table_projects": table_projects,
        "table_ideas": table_ideas,
    }


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_record(base_token: str, table_id: str, fields: dict) -> dict:
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["record"]


async def search_records(base_token: str, table_id: str, filter_expr: str = "") -> list[dict]:
    params = {"page_size": 100}
    if filter_expr:
        params["filter"] = filter_expr
    resp = await _client.get(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
        headers=await _headers(),
        params=params,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    items = data.get("items", [])
    return [{"record_id": r["record_id"], **r["fields"]} for r in items]


async def update_record(base_token: str, table_id: str, record_id: str, fields: dict) -> dict:
    resp = await _client.put(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    return resp.json()["data"]["record"]


async def delete_record(base_token: str, table_id: str, record_id: str):
    resp = await _client.delete(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")

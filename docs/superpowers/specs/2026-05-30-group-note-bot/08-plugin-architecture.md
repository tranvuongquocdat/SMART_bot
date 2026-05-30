[← Index](./README.md)

# §8. Plugin architecture

## 8.1 Plugin folder

Mỗi plugin = 1 thư mục trong `plugins/`:

```
plugins/
└── google_calendar/
    ├── manifest.toml          # metadata
    ├── tools.py               # tool definitions + handlers
    ├── auth.py                # OAuth start + callback
    ├── settings_schema.json   # config form schema (JSON Schema)
    ├── README.md              # cho user đọc khi enable
    └── assets/
        └── icon.svg
```

## 8.2 Manifest

```toml
# plugins/google_calendar/manifest.toml
id          = "google_calendar"
name        = "Google Calendar"
version     = "0.1.0"
description = "Push action item / deadline thành Calendar event"
icon        = "assets/icon.svg"

[auth]
type        = "oauth2"
scopes      = ["https://www.googleapis.com/auth/calendar.events"]

[capabilities]
tools       = ["create_event", "list_events", "delete_event"]
```

## 8.3 Tools

```python
# plugins/google_calendar/tools.py
from app.plugin_api import tool, ToolContext

@tool(
    name="gcal_create_event",
    description="Tạo Google Calendar event từ action item",
    parameters={
        "type": "object",
        "properties": {
            "title":        {"type": "string"},
            "start_iso":    {"type": "string"},
            "duration_min": {"type": "integer", "default": 30},
            "description":  {"type": "string"},
        },
        "required": ["title", "start_iso"],
    },
)
async def create_event(ctx: ToolContext, title, start_iso, duration_min=30, description=""):
    token    = await ctx.get_oauth_token()
    settings = await ctx.get_settings()   # default_calendar_id, ...
    # call Google API
    ...
    return {"event_id": "...", "url": "..."}
```

Tool prefix `gcal_` tránh collision với core tool / plugin khác.

## 8.4 OAuth flow

```
1. Sếp click "Connect" trên web /plugins/google_calendar
2. Web call plugin.auth.start(boss_id) → trả về URL Google consent
3. Sếp click URL, login Google, accept scopes
4. Google redirect về /api/oauth/plugin/google_calendar/callback?code=...&state=...
5. Endpoint gọi plugin.auth.callback(boss_id, code) → exchange code
   lấy access_token + refresh_token
6. Lưu vào boss_integrations (auth_blob_enc, encrypted)
7. Redirect web về /plugins/google_calendar (đã connected)
```

Schema:

```sql
boss_integrations (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  plugin_id       TEXT NOT NULL,
  enabled         BOOLEAN NOT NULL DEFAULT TRUE,
  auth_blob_enc   BYTEA,                  -- encrypted token JSON
  settings_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
  connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, plugin_id)
);
```

## 8.5 Settings auto-render

`settings_schema.json` (JSON Schema chuẩn):

```json
{
  "type": "object",
  "properties": {
    "default_calendar_id": {
      "type": "string",
      "title": "Calendar mặc định",
      "x-enum-from": "list_calendars"
    },
    "auto_push_deadlines": {
      "type": "boolean",
      "title": "Tự đẩy deadline từ group lên Calendar",
      "default": false
    },
    "reminder_minutes": {
      "type": "integer",
      "title": "Nhắc trước (phút)",
      "default": 30,
      "minimum": 0,
      "maximum": 1440
    }
  },
  "required": ["default_calendar_id"]
}
```

Web có generic `<JsonSchemaForm>` (HTMX + Alpine) render thành form HTML.
`x-enum-from` = gọi 1 plugin handler để populate dropdown động (vd list
calendar Google của sếp).

## 8.6 Plugin loading

App startup scan `plugins/`:

```python
plugins_registry: dict[str, Plugin] = {}

for plugin_dir in PLUGINS_ROOT.glob("*/"):
    manifest = load_manifest(plugin_dir / "manifest.toml")
    tools_module = import_module(f"plugins.{plugin_dir.name}.tools")
    auth_module  = import_module(f"plugins.{plugin_dir.name}.auth")
    plugins_registry[manifest.id] = Plugin(manifest, tools_module, auth_module)
```

Thêm plugin = drop folder + restart server. **Không sửa core.**

## 8.7 Per-boss tool composition

Khi build context cho LLM call:

```python
tools = list(CORE_TOOLS)
enabled = await boss_integrations_repo.list_enabled(boss_id)
for inst in enabled:
    plugin = plugins_registry[inst.plugin_id]
    tools.extend(plugin.get_tools(boss_id))
```

Boss A không bật Notion → LLM của boss A không thấy Notion tool. Context
gọn, không hallucinate gọi sai.

## 8.8 Mở

- **(mở) Plugin sandboxing** — plugin code in-process, có quyền đọc DB
  & file system. Phase 0 trust mọi plugin do em viết. Phase 2 nếu mở
  3rd-party → tách process (kiểu MCP) hoặc Wasm.
- **(mở) Plugin version & migrate** — manifest.version tăng → khi nào
  invalidate auth/settings? Hoãn.

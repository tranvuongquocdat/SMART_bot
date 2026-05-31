[← Index](./README.md)

# §8. Plugin architecture

## 8.0 Plugin vs Channel

| Loại | Định nghĩa | Ví dụ |
|---|---|---|
| **Channel** | Adapter cho 1 platform messaging (inbound + outbound). Sở hữu `bot_account`, đăng ký webhook/poll. | Zalo personal (MVP); Telegram + Messenger + WhatsApp (Phase 1+) |
| **Plugin** | Tool/integration cho 1 service ngoài. Per-boss enable + OAuth. Tool gọi từ agent. | Google Calendar, Lark Base, Notion |

**Lark Base = plugin**, không phải channel. Sếp connect Lark Base để bot
push action item / sync data — không nhận message từ Lark Messenger.

## 8.1 Plugin folder

Mỗi plugin = 1 thư mục trong `plugins/`:

```
plugins/
├── google_calendar/          # Phase 1
│   ├── manifest.toml
│   ├── tools.py
│   ├── auth.py
│   ├── settings_schema.json
│   ├── README.md
│   └── assets/icon.svg
└── lark_base/                # Phase 1
    ├── manifest.toml
    ├── tools.py              # create_record, query_table, update_record
    ├── auth.py               # Lark OAuth user-access-token
    └── ...
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

## 8.8 Đã chốt & defer

- Plugin = service integration, không phải channel. Lark Base là plugin Phase 1.
- Phase 0 trust mọi plugin do team viết (in-process). Sandboxing (Wasm/MCP-style subprocess) → Phase 2 nếu mở 3rd-party.
- Plugin version migrate → defer; tracking qua `manifest.version` nhưng chưa enforce.

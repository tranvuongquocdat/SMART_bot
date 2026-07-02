from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_DSN: str
    QDRANT_URL: str = "http://localhost:6333"

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    SESSION_SECRET: str
    FERNET_KEY: str
    OAUTH_REDIRECT_WHITELIST: str = ""

    SUPERADMIN_EMAILS: str = ""

    # Chấp nhận cả tên quen thuộc OPENAI_API_KEY / GROQ_API_KEY
    PLATFORM_OPENAI_API_KEY: str = Field(
        "", validation_alias=AliasChoices("PLATFORM_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    PLATFORM_GROQ_API_KEY: str = Field(
        "", validation_alias=AliasChoices("PLATFORM_GROQ_API_KEY", "GROQ_API_KEY")
    )

    BANK_ACCOUNT_NUMBER: str = ""
    BANK_ACCOUNT_NAME: str = ""
    BANK_BIN: str = ""

    DEFAULT_BOSS_COST_CAP_USD_DAILY: float = 5.0
    LOG_RAW_CONTENT: bool = False
    ENABLE_WEB_TEST_CHANNEL: bool = True

    # Model dùng để tự suy ra metadata (giá/khả năng/ngữ cảnh) khi boss thêm model.
    # Model nhỏ (gpt-4o-mini) nhớ giá sai → mặc định dùng model frontier; đổi qua env.
    AI_METADATA_MODEL_OPENAI: str = "gpt-5.4"
    AI_METADATA_MODEL_GROQ: str = "llama-3.3-70b-versatile"

    # Đường dẫn script bridge Zalo. Rỗng = bridge.js thật cạnh adapter.
    # Test/harness trỏ sang tests/fixtures/zalo/fake_bridge.js để chạy không cần
    # zca-js / acc Zalo thật.
    ZALO_BRIDGE_SCRIPT: str = ""

    # PDPL retention: tin nhắn THÔ (messages/outbound_messages) giữ tối đa N
    # ngày; spine knowledge không đụng. 0 = tắt (không xoá gì).
    RAW_MESSAGE_RETENTION_DAYS: int = 180

    @field_validator(
        "PLATFORM_OPENAI_API_KEY",
        "PLATFORM_GROQ_API_KEY",
        "BANK_ACCOUNT_NUMBER",
        "BANK_ACCOUNT_NAME",
        "BANK_BIN",
        mode="before",
    )
    @classmethod
    def _strip_whitespace(cls, v):
        return v.strip() if isinstance(v, str) else v

    @property
    def superadmin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.SUPERADMIN_EMAILS.split(",") if e.strip()}

    @property
    def redirect_whitelist(self) -> set[str]:
        return {u.strip() for u in self.OAUTH_REDIRECT_WHITELIST.split(",") if u.strip()}


settings = Settings()  # raises if required vars missing

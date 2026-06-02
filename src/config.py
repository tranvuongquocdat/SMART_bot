from pydantic import Field
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

    PLATFORM_OPENAI_API_KEY: str = ""
    PLATFORM_GROQ_API_KEY: str = ""

    DEFAULT_BOSS_COST_CAP_USD_DAILY: float = 5.0
    LOG_RAW_CONTENT: bool = False
    ENABLE_WEB_TEST_CHANNEL: bool = True

    @property
    def superadmin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.SUPERADMIN_EMAILS.split(",") if e.strip()}

    @property
    def redirect_whitelist(self) -> set[str]:
        return {u.strip() for u in self.OAUTH_REDIRECT_WHITELIST.split(",") if u.strip()}


settings = Settings()  # raises if required vars missing

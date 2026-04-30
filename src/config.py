from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    lark_app_id: str
    lark_app_secret: str

    openai_api_key: str
    openai_chat_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dim: int = 1536      # text-embedding-3-small = 1536

    qdrant_url: str = "http://qdrant:6333"

    cohere_api_key: str

    db_path: str = "data/history.db"
    timezone: str = "Asia/Ho_Chi_Minh"
    recent_messages: int = 15
    rag_messages: int = 8

    # Forward-compat (Phase 3): per-boss LLM credential encryption.
    # Empty = encryption disabled (no boss can have an encrypted key column populated).
    boss_credential_encryption_key: str = ""

    # Phase 5d: 'json' emits one JSON record per log line (for log shippers);
    # anything else uses the existing human-readable format.
    log_format: str = "human"

    # Zalo channel (Phase 6b demo, single account).
    # Disabled by default; set zalo_enabled=true + zalo_session_path to enable.
    zalo_enabled: bool = False
    zalo_node_path: str = "node"
    zalo_session_path: str = ""
    # Phrase a sếp says (DM only) to introduce themselves to the bot before
    # they're a registered boss. Other DMs from non-bosses are dropped to
    # keep the personal-account use case manageable.
    zalo_onboard_phrase: str = "thư ký ơi"

    model_config = {"env_file": ".env", "extra": "ignore"}

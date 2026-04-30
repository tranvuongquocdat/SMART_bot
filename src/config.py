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

    model_config = {"env_file": ".env", "extra": "ignore"}

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    lark_app_id: str
    lark_app_secret: str

    openai_api_key: str
    openai_chat_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"

    qdrant_url: str = "http://qdrant:6333"

    cohere_api_key: str

    db_path: str = "data/history.db"
    timezone: str = "Asia/Ho_Chi_Minh"
    recent_messages: int = 15
    rag_messages: int = 8

    model_config = {"env_file": ".env"}

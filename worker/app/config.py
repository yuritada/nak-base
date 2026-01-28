"""
Phase 1 Worker設定
RAG基盤対応
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://nakbase:nakbase_secret@db:5432/nakbase"
    redis_url: str = "redis://redis:6379/0"
    ollama_url: str = "http://ollama:11434"
    parser_url: str = "http://parser:8001"
    storage_path: str = "/storage"
    mock_mode: bool = True  # デフォルトをTrue(デモモード)にする
    debug_mode: bool = False

    # Embedding settings
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # LLM settings
    llm_model: str = "gemma2:2b"

    # Retry settings
    max_retries: int = 3

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

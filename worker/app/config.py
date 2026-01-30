"""
MVP版 Worker設定
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

    # Embedding設定 (Phase 1-3 RAG)
    embedding_model: str = "nomic-embed-text"  # Ollamaで使用するEmbeddingモデル
    embedding_dim: int = 768  # nomic-embed-textは768次元
    rag_top_k: int = 5  # セマンティック検索で取得するチャンク数

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

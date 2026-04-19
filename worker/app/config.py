from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # model_config は pydantic-settings v2 の書き方
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    database_url: str
    redis_url: str
    ollama_url: str
    parser_url: str
    storage_path: str = "/storage"
    mock_mode: bool = True
    debug_mode: bool = False

    # Embedding設定 (Phase 1-3 RAG)
    embedding_model: str = "nomic-embed-text"  # Ollamaで使用するEmbeddingモデル
    embedding_dim: int = 768  # nomic-embed-textは768次元
    rag_top_k: int = 5  # セマンティック検索で取得するチャンク数


@lru_cache()
def get_settings():
    return Settings()

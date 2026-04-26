from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # model_config は pydantic-settings v2 の書き方
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24時間
    storage_path: str = "/storage"
    debug_mode: bool = False


@lru_cache()
def get_settings():
    """アプリ全体で共有される設定を取得するための関数"""
    return Settings()

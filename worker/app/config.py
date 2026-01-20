from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://nakbase:nakbase_secret@db:5432/nakbase"
    redis_url: str = "redis://redis:6379/0"
    gemini_api_key: str = ""
    google_drive_folder_id: str = ""
    google_application_credentials: str = "/app/secrets/service-account.json"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

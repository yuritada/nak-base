from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional


LLMProvider = Literal["gemini", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    database_url: str
    redis_url: str
    ollama_url: str
    parser_url: str
    storage_path: str = "/storage"
    mock_mode: bool = False
    debug_mode: bool = False

    # Embedding設定 (Phase 1-3 RAG)
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    rag_top_k: int = 5

    # ==========================================
    # Multi-Agent Pipeline (Phase 2)
    # ==========================================
    # 使用するLLMプロバイダ: "gemini" or "openai"
    llm_provider: LLMProvider = "gemini"

    # --- Gemini ---
    gemini_api_key: Optional[str] = None
    gemini_api_key_file: str = "/secrets/gemini_api_key"
    gemini_model_flash: str = "gemini-1.5-flash"
    gemini_model_pro: str = "gemini-1.5-pro"

    # --- OpenAI ---
    openai_api_key: Optional[str] = None
    openai_api_key_file: str = "/secrets/openai_api_key"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_pro: str = "gpt-4o"

    # 並列実行 / タイムアウト
    agent_timeout: int = 300
    agents_parallel: bool = True

    # ----- helpers -----
    @staticmethod
    def _read_secret_file(path_str: str) -> Optional[str]:
        try:
            p = Path(path_str)
            if p.exists():
                content = p.read_text(encoding="utf-8").strip()
                return content or None
        except Exception:
            pass
        return None

    def get_gemini_api_key(self) -> Optional[str]:
        """環境変数 → secretsファイル の順で API キーを取得"""
        if self.gemini_api_key:
            return self.gemini_api_key
        return self._read_secret_file(self.gemini_api_key_file)

    def get_openai_api_key(self) -> Optional[str]:
        """環境変数 → secretsファイル の順で API キーを取得"""
        if self.openai_api_key:
            return self.openai_api_key
        return self._read_secret_file(self.openai_api_key_file)

    def model_for(self, use_pro: bool) -> str:
        """現在のプロバイダで Pro/Fast に対応するモデル名を返す"""
        if self.llm_provider == "openai":
            return self.openai_model_pro if use_pro else self.openai_model_fast
        return self.gemini_model_pro if use_pro else self.gemini_model_flash


@lru_cache()
def get_settings():
    return Settings()

"""
OpenAI / GPT クライアント (マルチエージェント・パイプライン用)

- mock_mode: 既存のモックOllamaサーバーへ X-Agent-Type ヘッダ付きで転送
- 本番モード: openai SDK (>=1.0) で chat.completions.create を呼ぶ
"""
import os
import json
import uuid
import requests
from datetime import datetime
from typing import Optional

from ..config import get_settings

settings = get_settings()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # mock 環境では未インストールでも動く

_client: Optional["OpenAI"] = None


def _get_client() -> Optional["OpenAI"]:
    """OpenAIクライアントをAPIキーで初期化（一度だけ）"""
    global _client
    if _client is not None:
        return _client
    if OpenAI is None:
        print("openai SDK is not installed; cannot call live OpenAI API")
        return None
    api_key = settings.get_openai_api_key()
    if not api_key:
        print("OpenAI API key not found (env OPENAI_API_KEY or /secrets/openai_api_key)")
        return None
    _client = OpenAI(api_key=api_key)
    return _client


def _save_mock_log(agent_name: str, model: str, prompt: str) -> None:
    try:
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filepath = os.path.join(logs_dir, f"openai_{agent_name}_{timestamp}_{unique_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "agent": agent_name,
                "model": model,
                "prompt_length": len(prompt),
                "prompt": prompt,
            }, f, ensure_ascii=False, indent=2)
        if settings.debug_mode:
            print(f"【デバッグ】Mock OpenAI request saved: {filepath}")
    except Exception as e:
        print(f"Failed to save mock openai log: {e}")


def call_openai(
    prompt: str,
    *,
    agent_name: str,
    use_pro: bool = False,
    timeout: Optional[int] = None,
) -> str:
    """OpenAI を呼び出して生テキスト（JSON文字列を期待）を返す"""
    model_name = settings.openai_model_pro if use_pro else settings.openai_model_fast
    timeout = timeout or settings.agent_timeout

    # ---- Mock mode: モックOllamaサーバーへ転送 ----
    if settings.mock_mode:
        _save_mock_log(agent_name, model_name, prompt)
        try:
            response = requests.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False},
                headers={"X-Agent-Type": agent_name},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"Mock OpenAI call failed for {agent_name}: {e}")
            return ""

    # ---- Live mode ----
    client = _get_client()
    if client is None:
        return ""

    try:
        result = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        return result.choices[0].message.content or ""
    except Exception as e:
        print(f"OpenAI API call failed for {agent_name}: {e}")
        return ""

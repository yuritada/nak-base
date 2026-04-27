"""
Gemini API クライアント (マルチエージェント・パイプライン用)

- mock_mode の場合: Ollamaモックサーバーへリダイレクトして固定/設定可能なレスポンスを得る
- 本番モード:       google-generativeai SDK で Flash / Pro を切り替え
"""
import os
import json
import time
import uuid
import requests
from datetime import datetime
from typing import Optional

from ..config import get_settings

settings = get_settings()

# google-generativeai は本番でのみ必要
try:
    import google.generativeai as genai
except ImportError:  # mock環境では未インストールでも動く
    genai = None

_configured = False


def _ensure_configured() -> bool:
    """Gemini SDKをAPIキーで初期化（一度だけ）"""
    global _configured
    if _configured:
        return True
    if genai is None:
        print("google-generativeai is not installed; cannot call live Gemini API")
        return False
    api_key = settings.get_gemini_api_key()
    if not api_key:
        print("Gemini API key not found (env GEMINI_API_KEY or /secrets/gemini_api_key)")
        return False
    genai.configure(api_key=api_key)
    _configured = True
    return True


def _save_mock_log(agent_name: str, model: str, prompt: str) -> None:
    """mock_modeでGemini呼び出しが発生した場合、ログを残す（デバッグ用）"""
    try:
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filepath = os.path.join(logs_dir, f"gemini_{agent_name}_{timestamp}_{unique_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "agent": agent_name,
                "model": model,
                "prompt_length": len(prompt),
                "prompt": prompt,
            }, f, ensure_ascii=False, indent=2)
        if settings.debug_mode:
            print(f"【デバッグ】Mock Gemini request saved: {filepath}")
    except Exception as e:
        print(f"Failed to save mock gemini log: {e}")


def call_gemini(
    prompt: str,
    *,
    agent_name: str,
    use_pro: bool = False,
    timeout: Optional[int] = None,
) -> str:
    """
    Gemini を呼び出して生テキストを返す。

    Args:
        prompt: 完成済みのプロンプト全文
        agent_name: linter / logic / rag / diff など（ログ・モック判別用）
        use_pro: True なら gemini-1.5-pro、False なら flash
        timeout: SDK には直接渡せないが、mockモード経由のHTTP呼び出しに使用

    Returns:
        モデルが返した生テキスト（JSON 文字列であることを期待）
    """
    model_name = settings.gemini_model_pro if use_pro else settings.gemini_model_flash
    timeout = timeout or settings.agent_timeout

    # ---- Mock mode: モックOllamaサーバーへ転送 ----
    if settings.mock_mode:
        _save_mock_log(agent_name, model_name, prompt)
        try:
            # mock_ollama 側で X-Agent-Type ヘッダを見て agent_name 別のレスポンスを返す
            response = requests.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                },
                headers={"X-Agent-Type": agent_name},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"Mock Gemini call failed for {agent_name}: {e}")
            return ""

    # ---- Live mode: 実際の Gemini API ----
    if not _ensure_configured():
        # APIキー未設定時は空文字を返してエージェント側で空応答扱いにする
        return ""

    try:
        model = genai.GenerativeModel(model_name)
        result = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
            },
        )
        return getattr(result, "text", "") or ""
    except Exception as e:
        print(f"Gemini API call failed for {agent_name}: {e}")
        return ""

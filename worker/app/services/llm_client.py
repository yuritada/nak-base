"""
LLMディスパッチャ
- settings.llm_provider に応じて Gemini / OpenAI を切り替える
- BaseAgent からはこの call_llm() のみを使用
"""
from typing import Optional

from ..config import get_settings
from .gemini_client import call_gemini
from .openai_client import call_openai

settings = get_settings()


def call_llm(
    prompt: str,
    *,
    agent_name: str,
    use_pro: bool = False,
    timeout: Optional[int] = None,
) -> str:
    """設定された LLM プロバイダで生テキスト（JSON文字列）を取得"""
    provider = (settings.llm_provider or "gemini").lower()

    if settings.debug_mode:
        model = settings.model_for(use_pro)
        print(f"【デバッグ】LLM call: provider={provider}, model={model}, agent={agent_name}")

    if provider == "openai":
        return call_openai(prompt, agent_name=agent_name, use_pro=use_pro, timeout=timeout)

    # default: gemini
    return call_gemini(prompt, agent_name=agent_name, use_pro=use_pro, timeout=timeout)

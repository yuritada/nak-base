"""
BaseAgent: 各エージェント共通の基盤

責務:
- システムプロンプト（worker/app/prompts/<name>.md）の読み込み
- ユーザーコンテキストの整形
- LLM 呼び出し（Gemini Flash / Pro 切替、mock時はモックOllamaへ転送）
- 応答 JSON のロバストなパース
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import get_settings
from ..prompts import load_prompt
from ..services.llm_client import call_llm

settings = get_settings()


@dataclass
class AgentResult:
    """エージェント実行結果"""
    name: str
    output: dict = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_sec: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


class BaseAgent:
    """共通基底クラス。サブクラスは name / prompt_template / use_pro / build_user_prompt を上書きする。"""

    name: str = "base"
    prompt_template: str = ""  # prompts/ 内のファイル名（拡張子なし）
    use_pro: bool = False      # True なら gemini-1.5-pro

    def __init__(self):
        if not self.prompt_template:
            raise ValueError(f"{self.__class__.__name__}.prompt_template is not set")

    # ----- public -----
    def run(self, context: dict) -> AgentResult:
        """同期実行のエントリポイント"""
        import time
        t0 = time.time()
        try:
            user_prompt = self.build_user_prompt(context)
            if user_prompt is None:
                return AgentResult(name=self.name, output={}, elapsed_sec=time.time() - t0)

            full_prompt = self._compose_prompt(user_prompt)
            if settings.debug_mode:
                print(f"【デバッグ】{self.name} プロンプト長: {len(full_prompt)}文字")

            raw = call_llm(full_prompt, agent_name=self.name, use_pro=self.use_pro)
            parsed = self._parse_json(raw)
            return AgentResult(name=self.name, output=parsed, elapsed_sec=time.time() - t0)

        except Exception as e:
            print(f"Agent {self.name} failed: {e}")
            return AgentResult(name=self.name, output={}, error=str(e), elapsed_sec=time.time() - t0)

    # ----- to override -----
    def build_user_prompt(self, context: dict) -> Optional[str]:
        """エージェント固有のユーザープロンプトを組み立てる。
        Noneを返すとそのエージェントはスキップ扱い（出力は空dict）。"""
        raise NotImplementedError

    # ----- helpers -----
    def _compose_prompt(self, user_prompt: str) -> str:
        system = load_prompt(self.prompt_template)
        return f"{system}\n\n---\n\n{user_prompt}"

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """LLM出力からJSONを抽出してdictへ。失敗時は {raw_text: ...} を返す。"""
        if not raw:
            return {}
        text = raw.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # ```json ... ``` ブロック
        if "```json" in text:
            try:
                fragment = text.split("```json", 1)[1].split("```", 1)[0]
                return json.loads(fragment)
            except (IndexError, json.JSONDecodeError):
                pass
        if "```" in text:
            try:
                fragment = text.split("```", 1)[1].split("```", 1)[0]
                return json.loads(fragment)
            except (IndexError, json.JSONDecodeError):
                pass

        # 中括弧の最初〜最後を抽出
        if "{" in text and "}" in text:
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                pass

        return {"raw_text": text[:1000]}

    @staticmethod
    def _truncate(text: Any, limit: int) -> str:
        s = str(text or "")
        return s if len(s) <= limit else s[:limit] + "\n... (以下省略)"

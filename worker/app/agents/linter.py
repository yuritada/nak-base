"""
Linter Agent: 学会フォーマット違反 + 誤字脱字検出
- conference_rules テーブルの format_rules / style_guide をシステムプロンプトに注入
- 軽量タスクなので Flash を使用
"""
import json
from typing import Optional

from .base import BaseAgent


class LinterAgent(BaseAgent):
    name = "linter"
    prompt_template = "linter"
    use_pro = False

    PAPER_LIMIT = 12000  # Linter は本文長めに見る

    def build_user_prompt(self, context: dict) -> Optional[str]:
        paper_text: str = context.get("paper_text", "") or ""
        if not paper_text.strip():
            return None

        conf = context.get("conference_context") or {}
        conf_block = json.dumps(
            {
                "name": conf.get("name", "(指定なし)"),
                "format_rules": conf.get("format_rules", {}),
                "style_guide": conf.get("style_guide", ""),
            },
            ensure_ascii=False,
            indent=2,
        )

        return (
            "## 投稿規定（JSON）\n"
            f"```json\n{conf_block}\n```\n\n"
            "## 論文テキスト\n"
            f"{self._truncate(paper_text, self.PAPER_LIMIT)}\n\n"
            "## 回答（JSON形式のみ）"
        )

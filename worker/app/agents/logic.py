"""
Logic Agent: 章立て・論理整合性のチェック
- 論文全文を長文コンテキストとして扱う
- 高度な分析が必要なため Pro を使用
"""
from typing import Optional

from .base import BaseAgent


class LogicAgent(BaseAgent):
    name = "logic"
    prompt_template = "logic"
    use_pro = True  # ハイブリッド構成: 論理判定は Pro

    PAPER_LIMIT = 30000  # Pro の長文コンテキストを活かす

    def build_user_prompt(self, context: dict) -> Optional[str]:
        paper_text: str = context.get("paper_text", "") or ""
        if not paper_text.strip():
            return None

        return (
            "## 論文テキスト\n"
            f"{self._truncate(paper_text, self.PAPER_LIMIT)}\n\n"
            "## 回答（JSON形式のみ）"
        )

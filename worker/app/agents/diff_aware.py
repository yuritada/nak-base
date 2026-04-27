"""
Diff-Aware Agent: 前回 → 今回の改稿が前回フィードバックを反映できているかを評価
- 高度な対応判定が必要なので Pro を使用
"""
import json
from typing import Optional

from .base import BaseAgent


class DiffAwareAgent(BaseAgent):
    name = "diff"
    prompt_template = "diff_aware"
    use_pro = True  # ハイブリッド構成: 差分判定は Pro

    DIFF_LIMIT = 6000

    def build_user_prompt(self, context: dict) -> Optional[str]:
        prev_fb = context.get("previous_feedback") or {}
        diff_text: str = context.get("diff_text", "") or ""

        # 前回FBも差分も無ければ初回提出 → スキップ（空dictでマージされる）
        if not prev_fb and not diff_text.strip():
            return None

        prev_block = json.dumps(prev_fb, ensure_ascii=False, indent=2) if prev_fb else "(なし)"
        diff_block = self._truncate(diff_text, self.DIFF_LIMIT) if diff_text.strip() else "(差分なし)"

        return (
            "## 前回のフィードバック\n"
            f"```json\n{prev_block}\n```\n\n"
            "## 前回 → 今回の差分（Unified Diff）\n"
            f"```diff\n{diff_block}\n```\n\n"
            "## 回答（JSON形式のみ）"
        )

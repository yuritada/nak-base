"""
RAG Agent: pgvector で取得した関連チャンクから示唆を抽出
- 軽量なのでFlashを使用
"""
from typing import Optional

from .base import BaseAgent


class RagAgent(BaseAgent):
    name = "rag"
    prompt_template = "rag"
    use_pro = False

    PAPER_PREVIEW = 3000
    CHUNK_LIMIT = 1500

    def build_user_prompt(self, context: dict) -> Optional[str]:
        paper_text: str = context.get("paper_text", "") or ""
        rag_ctx = context.get("rag_context") or {}
        chunks = rag_ctx.get("related_chunks", []) or []

        if not paper_text.strip():
            return None

        # 関連チャンクが0件でもエージェントは走らせる（"関連知見なし"を出させる）
        formatted = []
        for i, c in enumerate(chunks, 1):
            formatted.append(
                f"### [{i}] {c.get('paper_title', '不明')} / {c.get('section') or 'セクション不明'} "
                f"(p.{c.get('page_number', '-')}, sim={c.get('similarity', 0):.3f})\n"
                f"{self._truncate(c.get('content', ''), self.CHUNK_LIMIT)}"
            )
        chunks_block = "\n\n".join(formatted) if formatted else "(関連チャンクなし)"

        return (
            "## 現在の論文（抜粋）\n"
            f"{self._truncate(paper_text, self.PAPER_PREVIEW)}\n\n"
            "## 関連する過去論文チャンク\n"
            f"{chunks_block}\n\n"
            "## 回答（JSON形式のみ）"
        )

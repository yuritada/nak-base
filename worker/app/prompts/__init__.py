"""
プロンプトテンプレートをファイルから読み込むユーティリティ。
"""
from pathlib import Path
from functools import lru_cache

PROMPT_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """prompts/<name>.md を読み込む（キャッシュ付き）"""
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")

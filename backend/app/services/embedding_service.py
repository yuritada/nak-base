"""
Embedding Service
Phase 1-3: RAG用ベクトル生成

学会ルールなどのテキストをベクトル化するサービス
"""
import os
import requests
from typing import List

# 設定
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def generate_embedding(text: str) -> List[float]:
    """
    テキストからベクトルを生成

    Args:
        text: ベクトル化するテキスト

    Returns:
        768次元のベクトル（List[float]）

    Note:
        - Mockモード: 全要素0.1のダミーベクトルを返す
        - 本番モード: Ollama /api/embeddings を呼び出す
    """
    # Mockモード: ダミーベクトルを返す
    if MOCK_MODE:
        return [0.1] * EMBEDDING_DIM

    # 本番モード: Ollama Embedding API を呼び出す
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": text[:8000]  # テキスト長制限
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result.get("embedding", [0.0] * EMBEDDING_DIM)

    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return [0.0] * EMBEDDING_DIM


def generate_conference_rule_embedding(name: str, style_guide: str, format_rules: dict = None) -> List[float]:
    """
    学会ルールからEmbeddingを生成

    Args:
        name: 学会名
        style_guide: スタイルガイドテキスト
        format_rules: フォーマット規定（JSON）

    Returns:
        768次元のベクトル
    """
    # テキストを組み立て
    parts = [f"学会名: {name}"]

    if format_rules:
        rules_text = ", ".join([f"{k}: {v}" for k, v in format_rules.items()])
        parts.append(f"フォーマット規定: {rules_text}")

    if style_guide:
        parts.append(f"スタイルガイド: {style_guide}")

    combined_text = "\n".join(parts)

    return generate_embedding(combined_text)

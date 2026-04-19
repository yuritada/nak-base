"""
Ollama API Client
- Embedding生成
- LLMによるテキスト分析
"""
import os
import json
import time
import uuid
import requests
from datetime import datetime
from typing import List, Optional

from ..config import get_settings

settings = get_settings()


def generate_embedding(text_input: str) -> List[float]:
    """
    テキストからベクトルを生成

    Args:
        text_input: ベクトル化するテキスト

    Returns:
        ベクトル（List[float]）

    Note:
        - Mockモード: 全要素0.1のダミーベクトルを即座に返す
        - 本番モード: Ollama /api/embeddings を呼び出す
    """
    # Mockモード: ダミーベクトルを返す（開発用）
    if settings.mock_mode:
        if settings.debug_mode:
            print(f"【デバッグ】Mock Embedding生成: {len(text_input)}文字 -> {settings.embedding_dim}次元ダミーベクトル")
        return [0.1] * settings.embedding_dim

    # 本番モード: Ollama Embedding API を呼び出す
    try:
        response = requests.post(
            f"{settings.ollama_url}/api/embeddings",
            json={
                "model": settings.embedding_model,
                "prompt": text_input[:8000]  # テキスト長制限
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        embedding = result.get("embedding", [])
        if settings.debug_mode:
            print(f"【デバッグ】Embedding生成完了: {len(text_input)}文字 -> {len(embedding)}次元")

        return embedding

    except requests.exceptions.RequestException as e:
        print(f"Ollama embedding API request failed: {e}")
        # エラー時はダミーベクトルを返す
        return [0.0] * settings.embedding_dim
    except Exception as e:
        print(f"Embedding generation failed unexpectedly: {e}")
        return [0.0] * settings.embedding_dim


def call_ollama_completion(prompt: str, prompt_components: Optional[dict] = None) -> dict:
    """
    Ollamaを呼び出してテキスト分析

    Args:
        prompt: LLMに送信するプロンプト文字列
        prompt_components: プロンプトの構造化データ（Mockモード時のログ保存用）

    Mockモード時はリクエストJSONをログファイルに保存し、
    安全なダミーデータを返却する
    """
    # Mockモード: リクエストをログに保存し、ダミーレスポンスを返す
    if settings.mock_mode:
        print("Mock mode: Saving request to log file and returning dummy response...")
        time.sleep(1)

        # logsディレクトリが存在しない場合は作成
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)

        # ファイル名を生成: ollama_req_{YYYYMMDD_HHMMSS}_{UUID}.json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"ollama_req_{timestamp}_{unique_id}.json"
        filepath = os.path.join(logs_dir, filename)

        # 保存するデータを決定
        log_data = {
            "type": "structured_prompt" if prompt_components else "raw_prompt",
            "timestamp": timestamp,
            "model": "gemma2:2b",
            "prompt_length": len(prompt),
            "components": prompt_components if prompt_components else None,
            "raw_prompt": prompt if not prompt_components else None
        }

        # JSONファイルとして保存（日本語対応）
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        print(f"Mock mode: Request saved to {filepath}")

        # フロントエンドがエラーを起こさない安全なダミーデータを返却
        return {
            "summary": "【Mockモード】これはダミーの要約です。プロンプトの内容は logs フォルダ内のJSONファイルを確認してください。",
            "typos": ["ダミー誤字1", "ダミー誤字2"],
            "suggestions": ["これはダミーの改善提案です。", "MockモードのためLLM推論は行われていません。"],
            "improvements_from_previous": ["前回の指摘は修正されています（ダミー判定）"]
        }

    # 実際のOllama呼び出し
    try:
        response = requests.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": "gemma2:2b",
                "prompt": prompt,
                "stream": False
            },
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        response_text = result.get("response", "")

        # JSONをパース
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            elif "{" in response_text:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                json_str = response_text[start:end]
            else:
                json_str = response_text

            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError, ValueError) as e:
            print(f"Failed to parse Ollama response as JSON: {e}")
            return {
                "summary": response_text[:500],
                "typos": [],
                "suggestions": ["AIの応答をJSONとしてパースできませんでした"]
            }
    except requests.exceptions.RequestException as e:
        print(f"Ollama completion API request failed: {e}")
        return {
            "summary": f"Ollama APIへの接続に失敗しました: {e}",
            "typos": [],
            "suggestions": []
        }
    except Exception as e:
        print(f"Ollama completion failed unexpectedly: {e}")
        return {
            "summary": f"予期せぬエラーが発生しました: {e}",
            "typos": [],
            "suggestions": []
        }

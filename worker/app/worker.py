"""
Phase 1 AI Inference Worker
Embedding生成 + RAG基盤
ステータス遷移: pending -> parsing -> rag -> llm -> completed / error
"""
import redis
import time
import requests
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .config import get_settings
from .database import get_db_session
from .models import InferenceTask, File, Embedding, Feedback, Version, Paper
from .diagnostics import run_diagnostics

settings = get_settings()

TASK_QUEUE = "tasks"

# Ollamaプロンプト（分析用）
OLLAMA_PROMPT = """以下の論文のテキストを分析し、JSON形式で回答してください。

## 分析内容
1. 要約（summary）: 200文字程度で論文の概要を説明
2. スコア（scores）: 以下の項目を10点満点で評価
   - format: フォーマット・体裁
   - logic: 論理構成
   - content: 内容の質
3. コメント（comments）: 具体的な指摘事項のリスト

## 出力形式（JSON）
{{
  "summary": "論文の要約...",
  "scores": {{"format": 8, "logic": 7, "content": 8}},
  "comments": [
    {{"type": "typo", "text": "誤字: ○○"}},
    {{"type": "suggestion", "text": "改善提案: ○○"}}
  ]
}}

## 論文テキスト
{text}

## 回答（JSON形式）"""


def get_redis_client():
    return redis.from_url(settings.redis_url)


def call_parser(file_path: str) -> Dict[str, Any]:
    """
    Parserサービスを呼び出して構造化データを取得

    Returns:
        {
            "markdown_text": "...",
            "coordinates": [...],
            "chunks": [...],
            "page_count": N
        }
    """
    response = requests.post(
        f"{settings.parser_url}/parse",
        json={"file_path": file_path},
        timeout=120
    )
    response.raise_for_status()
    return response.json()


def generate_embedding(text: str) -> List[float]:
    """
    Ollama (nomic-embed-text) でembeddingを生成

    Returns:
        768次元のベクトル
    """
    if settings.mock_mode:
        # Mock: ゼロベクトルを返す
        return [0.0] * settings.embedding_dim

    response = requests.post(
        f"{settings.ollama_url}/api/embeddings",
        json={
            "model": settings.embedding_model,
            "prompt": text
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()["embedding"]


def call_ollama_analysis(text: str) -> Dict[str, Any]:
    """Ollamaを呼び出してテキスト分析（Mock対応版）"""

    if settings.mock_mode:
        print("[DEBUG] Mock mode: Returning demo data...")
        time.sleep(2)
        return {
            "summary": "本論文は、AIを活用した論文指導システムの構築について述べています。特に、マルチエージェントを用いたフィードバック層の導入により、教員の負担軽減と指導の質の向上を提案しています。",
            "scores": {
                "format": 8,
                "logic": 7,
                "content": 8
            },
            "comments": [
                {"type": "typo", "text": "1ページ目：『システムアーキテクチャ』のスペルミス"},
                {"type": "typo", "text": "3ページ目：『即時フィードバック』が『即時フイードバック』に"},
                {"type": "suggestion", "text": "先行研究の比較表を追加すると優位性が明確に"},
                {"type": "suggestion", "text": "図3の文字サイズ拡大を推奨"},
                {"type": "suggestion", "text": "結論で今後の展望を詳述"}
            ]
        }

    prompt = OLLAMA_PROMPT.format(text=text[:8000])

    response = requests.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": settings.llm_model,
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
    except Exception:
        return {
            "summary": response_text[:500],
            "scores": {},
            "comments": [{"type": "error", "text": "AIの応答をJSONとしてパースできませんでした"}]
        }


def update_task_status(db, task: InferenceTask, status: str, error_message: str = None):
    """タスクステータスを更新（タイムスタンプ含む）"""
    task.status = status
    task.updated_at = datetime.utcnow()

    if status == "parsing":
        task.started_at = datetime.utcnow()
    elif status in ["completed", "error"]:
        task.completed_at = datetime.utcnow()

    if error_message:
        task.error_message = error_message

    db.commit()

    if settings.debug_mode:
        print(f"[DEBUG] Task {task.id} status -> {status}")


def update_paper_status(db, paper: Paper, status: str):
    """Paper のステータスを更新"""
    paper.status = status
    paper.updated_at = datetime.utcnow()
    db.commit()


def process_task(task_id: int):
    """タスクを処理（Phase 1: embedding + feedback）"""
    db = get_db_session()

    try:
        # タスク取得
        task = db.query(InferenceTask).filter(InferenceTask.id == task_id).first()
        if not task:
            print(f"Task {task_id} not found")
            return

        # Version, File, Paper を取得
        version = task.version
        file = db.query(File).filter(File.version_id == version.id).first()
        if not file:
            update_task_status(db, task, "error", "No file found for version")
            return

        paper = version.paper

        print(f"Processing task {task_id} for file {file.file_path}")

        # ========================================
        # Phase: PARSING
        # ========================================
        update_task_status(db, task, "parsing")
        print("Phase: PARSING")

        parsed_data = call_parser(file.file_path)
        markdown_text = parsed_data["markdown_text"]
        coordinates = parsed_data["coordinates"]
        chunks = parsed_data["chunks"]
        page_count = parsed_data["page_count"]

        print(f"Parsed: {len(chunks)} chunks, {page_count} pages")

        # ========================================
        # Phase: RAG (Embedding Generation)
        # ========================================
        update_task_status(db, task, "rag")
        print("Phase: RAG (Embedding)")

        # 既存の embedding を削除（再処理の場合）
        db.query(Embedding).filter(Embedding.file_id == file.id).delete()
        db.commit()

        for idx, chunk in enumerate(chunks):
            # 対応する座標情報を取得（近似）
            coord = None
            if idx < len(coordinates):
                coord = coordinates[idx]

            # Embedding生成
            try:
                embedding_vector = generate_embedding(chunk)
            except Exception as e:
                print(f"[WARN] Embedding failed for chunk {idx}: {e}")
                embedding_vector = None

            # DB保存
            embedding = Embedding(
                file_id=file.id,
                chunk_index=idx,
                section_title=None,
                page_number=coord["page"] if coord else None,
                content_chunk=chunk,
                location_json={"page": coord["page"], "bbox": coord["bbox"]} if coord else None,
                embedding=embedding_vector
            )
            db.add(embedding)

        db.commit()
        print(f"Stored {len(chunks)} embeddings")

        # ========================================
        # Phase: LLM Analysis
        # ========================================
        update_task_status(db, task, "llm")
        print("Phase: LLM")

        result = call_ollama_analysis(markdown_text)

        # Feedback保存
        feedback = Feedback(
            version_id=version.id,
            task_id=task.id,
            score_json=result.get("scores"),
            comments_json=result.get("comments"),
            summary=result.get("summary")
        )
        db.add(feedback)
        db.commit()
        print("Feedback stored")

        # ========================================
        # Complete
        # ========================================
        update_task_status(db, task, "completed")
        update_paper_status(db, paper, "completed")
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        db.rollback()

        # リトライ処理
        task = db.query(InferenceTask).filter(InferenceTask.id == task_id).first()
        if task:
            task.retry_count += 1
            if task.retry_count >= settings.max_retries:
                update_task_status(db, task, "error", str(e))
                # Paper も error に
                if task.version and task.version.paper:
                    update_paper_status(db, task.version.paper, "error")
                print(f"Task {task_id} failed after {settings.max_retries} retries")
            else:
                # pending に戻してリトライ
                task.status = "pending"
                task.updated_at = datetime.utcnow()
                db.commit()
                # キューに再投入
                client = get_redis_client()
                client.rpush(TASK_QUEUE, str(task_id))
                print(f"Task {task_id} scheduled for retry ({task.retry_count}/{settings.max_retries})")

    finally:
        db.close()


def main():
    """Main worker loop."""
    print("=" * 50)
    print("Starting Phase 1 AI Inference Worker")
    print("=" * 50)

    # 起動診断
    run_diagnostics()

    print(f"Config:")
    print(f"  Redis: {settings.redis_url}")
    print(f"  Ollama: {settings.ollama_url}")
    print(f"  Parser: {settings.parser_url}")
    print(f"  Mock Mode: {settings.mock_mode}")
    print(f"  Embedding Model: {settings.embedding_model}")

    client = get_redis_client()

    # Wait for Redis to be ready
    while True:
        try:
            client.ping()
            print("Connected to Redis")
            break
        except redis.ConnectionError:
            print("Waiting for Redis...")
            time.sleep(2)

    print("Worker ready. Waiting for tasks...")

    while True:
        try:
            # Blocking pop from queue (timeout=30s)
            result = client.blpop(TASK_QUEUE, timeout=30)

            if result:
                _, data = result
                task_id = int(data)
                print(f"\n{'='*40}")
                print(f"Received task: {task_id}")
                print(f"{'='*40}")
                process_task(task_id)

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

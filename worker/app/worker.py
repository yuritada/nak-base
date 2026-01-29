"""
nak-base AI Inference Worker
Phase 1-1: 新スキーマ対応版

シングルプロセスで順次実行、リトライなし
"""
import redis
import time
import json
import requests
from datetime import datetime

from .config import get_settings
from .database import get_db_session
from .models import InferenceTask, File, Feedback, Paper, Version, TaskStatus, PaperStatus

settings = get_settings()

TASK_QUEUE = "tasks"

# Ollamaプロンプト（固定）
OLLAMA_PROMPT = """以下の論文のテキストを分析し、JSON形式で回答してください。

## 分析内容
1. 要約（summary）: 200文字程度で論文の概要を説明
2. 誤字脱字（typos）: 検出された誤字脱字のリスト
3. 改善提案（suggestions）: 論文を改善するための具体的な提案

## 出力形式（JSON）
{{
  "summary": "論文の要約...",
  "typos": ["誤字1", "誤字2"],
  "suggestions": ["提案1", "提案2", "提案3"]
}}

## 論文テキスト
{text}

## 回答（JSON形式）"""


def get_redis_client():
    return redis.from_url(settings.redis_url)


def call_parser(file_path: str) -> dict:
    """
    Parserサービスを呼び出してテキスト抽出
    Phase 1-2: 新形式（content, meta, pages, chunks）に対応
    """
    response = requests.post(
        f"{settings.parser_url}/parse",
        json={"file_path": file_path},
        timeout=120  # ZIP/TeX処理は時間がかかる場合がある
    )
    response.raise_for_status()
    result = response.json()

    # 新形式: content フィールドを使用
    # 旧形式（legacy）との互換性: text フィールドもチェック
    if "content" in result:
        return {
            "text": result["content"],
            "meta": result.get("meta", {}),
            "pages": result.get("pages", []),
            "chunks": result.get("chunks", [])
        }
    elif "text" in result:
        # Legacy形式
        return {
            "text": result["text"],
            "meta": {},
            "pages": [],
            "chunks": []
        }
    else:
        raise ValueError("Parser response missing both 'content' and 'text' fields")


def call_ollama(text: str) -> dict:
    """Ollamaを呼び出してテキスト分析（Mock対応版）"""

    # Mockモードが有効な場合は即座にデモデータを返す
    if settings.mock_mode:
        print("Mock mode: Returning demo data...")
        time.sleep(2)  # 処理してる感を出すための待ち時間
        return {
            "summary": "本論文は、AIを活用した論文指導システムの構築について述べています。特に、マルチエージェントを用いたフィードバック層の導入により、教員の負担軽減と指導の質の向上を提案しています。",
            "typos": [
                "1ページ目：『システムアーキテクチャ』→『システムアーキテクチャ』(スペルミス)",
                "3ページ目：『即時フィードバック』が『即時フイードバック』になっています"
            ],
            "suggestions": [
                "先行研究の比較表を追加すると、提案手法の優位性がより明確になります。",
                "図3の文字サイズが小さいため、拡大を推奨します。",
                "結論部分で、今後の展望についてもう少し詳しく触れてください。"
            ]
        }

    # 以下、元のOllama呼び出しロジック
    prompt = OLLAMA_PROMPT.format(text=text[:10000])  # 最初の10000文字のみ

    response = requests.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": "gemma2:2b",
            "prompt": prompt,
            "stream": False
        },
        timeout=300  # 5分タイムアウト
    )
    response.raise_for_status()

    result = response.json()
    response_text = result.get("response", "")

    # JSONをパースしてみる
    try:
        # JSONブロックを抽出
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
        # パースに失敗した場合はそのままテキストを返す
        return {
            "summary": response_text[:500],
            "typos": [],
            "suggestions": ["AIの応答をJSONとしてパースできませんでした"]
        }


def process_diagnosis_task(task_data: dict):
    """
    Process SYSTEM_DIAGNOSIS task (Debug mode only)
    Dynamically imports the diagnostic module from /app/tests/
    """
    print("=" * 50)
    print(" SYSTEM_DIAGNOSIS task received")
    print("=" * 50)

    try:
        # Dynamic import - only available in debug mode when tests are mounted
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "worker_check",
            "/app/tests/worker_check.py"
        )
        if spec and spec.loader:
            worker_check = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker_check)

            # Run worker diagnosis
            result = worker_check.run_worker_diagnosis(task_data)
            print(f"Diagnosis completed: {result}")
            return result
        else:
            print("ERROR: Could not load worker_check module")
            return None

    except FileNotFoundError:
        print("WARNING: /app/tests/worker_check.py not found")
        print("This is expected in production mode (tests not mounted)")
        return None
    except ImportError as e:
        print(f"WARNING: Could not import worker_check: {e}")
        print("This is expected in production mode")
        return None
    except Exception as e:
        print(f"ERROR in diagnosis task: {e}")
        return None


def process_task(task_id: int):
    """
    タスクを処理（新スキーマ対応版）

    フロー:
    1. InferenceTask を取得
    2. Version 経由で File（cache_path）を取得
    3. Parser でテキスト抽出
    4. Ollama で分析
    5. Feedback に結果を保存
    6. Paper/InferenceTask のステータスを更新
    """
    if settings.debug_mode:
        print(f"【デバッグ】タスク処理開始: Task ID={task_id}")

    db = get_db_session()

    try:
        # 1. InferenceTask を取得
        task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
        if not task:
            print(f"Task {task_id} not found")
            return

        # 2. Version と File を取得してファイルパスを特定
        version = task.version
        if not version:
            print(f"Version not found for task {task_id}")
            task.status = TaskStatus.ERROR
            task.error_message = "Version not found"
            db.commit()
            return

        # プライマリファイルを取得
        primary_file = db.query(File).filter(
            File.version_id == version.version_id,
            File.is_primary == True
        ).first()

        if not primary_file:
            # プライマリがなければ最初のファイルを使用
            primary_file = db.query(File).filter(
                File.version_id == version.version_id
            ).first()

        if not primary_file or not primary_file.cache_path:
            print(f"No file found for version {version.version_id}")
            task.status = TaskStatus.ERROR
            task.error_message = "No file found"
            db.commit()
            return

        file_path = primary_file.cache_path
        print(f"Processing task {task_id} for file {file_path}")

        # ステータス更新: PARSING
        task.status = TaskStatus.PARSING
        task.started_at = datetime.utcnow()
        db.commit()

        # 3. Parserを呼び出してテキスト抽出
        if settings.debug_mode:
            print(f"【デバッグ】Parserコンテナへテキスト抽出を依頼中... (Path: {file_path})")
        print("Calling Parser service...")
        parse_result = call_parser(file_path)
        parsed_text = parse_result["text"]
        parse_meta = parse_result.get("meta", {})
        if settings.debug_mode:
            print(f"【デバッグ】Parserより受領。抽出文字数: {len(parsed_text)}文字")
            if parse_meta:
                print(f"【デバッグ】ファイル種別: {parse_meta.get('file_type', 'unknown')}, ページ数: {parse_meta.get('num_pages', 0)}")
        print(f"Parsed text length: {len(parsed_text)}")

        # ステータス更新: LLM
        task.status = TaskStatus.LLM
        db.commit()

        # 4. Ollamaを呼び出して分析
        if settings.debug_mode:
            print(f"【デバッグ】AI推論(Ollama)を開始します...")
        print("Calling Ollama for analysis...")
        result = call_ollama(parsed_text)
        if settings.debug_mode:
            print(f"【デバッグ】AI推論完了。結果をDBに書き込みます。")
        print("Ollama analysis complete")

        # 5. Feedback に結果を保存
        feedback = Feedback(
            version_id=version.version_id,
            task_id=task.task_id,
            score_json=None,  # 将来的にスコア計算を実装
            comments_json={"typos": result.get("typos", []), "suggestions": result.get("suggestions", [])},
            overall_summary=result.get("summary", "")
        )
        db.add(feedback)

        # 6. ステータス更新: COMPLETED
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()

        # Paper のステータスも更新
        paper = version.paper
        if paper:
            paper.status = PaperStatus.COMPLETED

        db.commit()
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        db.rollback()

        # エラー時は即 status = ERROR
        try:
            task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
            if task:
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()

                # Paper のステータスも ERROR に
                if task.version and task.version.paper:
                    task.version.paper.status = PaperStatus.ERROR

                db.commit()
        except Exception as inner_e:
            print(f"Failed to update error status: {inner_e}")

    finally:
        db.close()


def parse_task_data(data: bytes) -> tuple:
    """
    Parse task data from Redis.
    Returns: (task_type, task_data)
    - For regular tasks: ("REGULAR", task_id as int)
    - For diagnosis tasks: ("SYSTEM_DIAGNOSIS", task_data as dict)
    """
    try:
        decoded = data.decode("utf-8")

        # Try to parse as JSON first
        try:
            task_data = json.loads(decoded)
            if isinstance(task_data, dict) and task_data.get("type") == "SYSTEM_DIAGNOSIS":
                return ("SYSTEM_DIAGNOSIS", task_data)
        except json.JSONDecodeError:
            pass

        # If not JSON or not diagnosis, treat as regular task ID
        return ("REGULAR", int(decoded))

    except Exception as e:
        print(f"Error parsing task data: {e}")
        return (None, None)


def main():
    """Main worker loop."""
    print("=" * 50)
    print(" NAK-BASE AI INFERENCE WORKER")
    print(" Phase 1-1: New Schema Support")
    print("=" * 50)
    print(f"Redis: {settings.redis_url}")
    print(f"Ollama: {settings.ollama_url}")
    print(f"Parser: {settings.parser_url}")
    print(f"Debug Mode: {settings.debug_mode}")
    print(f"Mock Mode: {settings.mock_mode}")

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
                task_type, task_data = parse_task_data(data)

                if task_type == "SYSTEM_DIAGNOSIS":
                    print(f"Received SYSTEM_DIAGNOSIS task")
                    process_diagnosis_task(task_data)

                elif task_type == "REGULAR":
                    task_id = task_data
                    print(f"Received regular task: {task_id}")
                    process_task(task_id)

                else:
                    print(f"Unknown task type, skipping: {data}")

            # タイムアウト時は何もせずループ継続

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

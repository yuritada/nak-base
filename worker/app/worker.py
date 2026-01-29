"""
MVP版 AI Inference Worker
シングルプロセスで順次実行、リトライなし

Phase 1-1: SYSTEM_DIAGNOSIS タスク対応追加
"""
import redis
import time
import json
import requests
from datetime import datetime

from .config import get_settings
from .database import get_db_session
from .models import Task

settings = get_settings()

TASK_QUEUE = "tasks"

# Ollamaプロンプト（固定）
OLLAMA_PROMPT = """以下の論文のテキストを分析し、JSON形式で回答してください。

## 分析内容
1. 要約（summary）: 200文字程度で論文の概要を説明
2. 誤字脱字（typos）: 検出された誤字脱字のリスト
3. 改善提案（suggestions）: 論文を改善するための具体的な提案

## 出力形式（JSON）
{
  "summary": "論文の要約...",
  "typos": ["誤字1", "誤字2"],
  "suggestions": ["提案1", "提案2", "提案3"]
}

## 論文テキスト
{text}

## 回答（JSON形式）"""


def get_redis_client():
    return redis.from_url(settings.redis_url)


def call_parser(file_path: str) -> str:
    """Parserサービスを呼び出してテキスト抽出"""
    response = requests.post(
        f"{settings.parser_url}/parse",
        json={"file_path": file_path},
        timeout=60
    )
    response.raise_for_status()
    return response.json()["text"]


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
    """タスクを処理"""
    if settings.debug_mode:
        print(f"【デバッグ】タスク処理開始: Task ID={task_id}")

    db = get_db_session()

    try:
        # タスク取得
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            print(f"Task {task_id} not found")
            return

        print(f"Processing task {task_id} for file {task.file_path}")

        # ステータス更新: processing
        task.status = "processing"
        db.commit()

        # 1. Parserを呼び出してテキスト抽出
        if settings.debug_mode:
            print(f"【デバッグ】Parserコンテナへテキスト抽出を依頼中... (Path: {task.file_path})")
        print("Calling Parser service...")
        parsed_text = call_parser(task.file_path)
        task.parsed_text = parsed_text
        db.commit()
        if settings.debug_mode:
            print(f"【デバッグ】Parserより受領。抽出文字数: {len(parsed_text)}文字")
        print(f"Parsed text length: {len(parsed_text)}")

        # 2. Ollamaを呼び出して分析
        if settings.debug_mode:
            print(f"【デバッグ】AI推論(Ollama)を開始します...")
        print("Calling Ollama for analysis...")
        result = call_ollama(parsed_text)
        task.result_json = result
        if settings.debug_mode:
            print(f"【デバッグ】AI推論完了。結果をDBに書き込みます。")
        print("Ollama analysis complete")

        # ステータス更新: completed
        task.status = "completed"
        db.commit()
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        db.rollback()

        # エラー時は即 status = error
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = "error"
            task.result_json = {"error": str(e)}
            db.commit()

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
    print("Starting MVP AI Inference Worker...")
    print(f"Redis: {settings.redis_url}")
    print(f"Ollama: {settings.ollama_url}")
    print(f"Parser: {settings.parser_url}")
    print(f"Debug Mode: {settings.debug_mode}")

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

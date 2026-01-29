"""
nak-base AI Inference Worker
Phase 1-3: RAG Pipeline + Context-Aware Prompt

シングルプロセスで順次実行、リトライなし
コンテキスト収集 → プロンプト組み立て → LLM呼び出し
"""
import redis
import time
import json
import requests
from datetime import datetime
from typing import Optional

from .config import get_settings
from .database import get_db_session
from .models import (
    InferenceTask, File, Feedback, Paper, Version,
    TaskStatus, PaperStatus, ConferenceRule
)

settings = get_settings()

TASK_QUEUE = "tasks"
NOTIFICATION_CHANNEL = "task_notifications"


def publish_notification(task_id: int, status: str, phase: str | None = None, error_message: str | None = None):
    """
    タスク通知をRedis Pub/Subに発行
    フロントエンドのSSEに中継される
    """
    try:
        client = get_redis_client()
        notification = {
            "task_id": task_id,
            "status": status,
            "phase": phase,
            "error_message": error_message,
        }
        client.publish(NOTIFICATION_CHANNEL, json.dumps(notification))
        if settings.debug_mode:
            print(f"【デバッグ】通知発行: {notification}")
    except Exception as e:
        print(f"Failed to publish notification: {e}")


def get_redis_client():
    return redis.from_url(settings.redis_url)


# ================== Context Gathering (Phase 1-3) ==================

def get_conference_context(db, conference_rule_id: Optional[str]) -> dict:
    """
    学会ルールのコンテキストを取得

    Returns:
        {
            "name": "学会名",
            "format_rules": {...},
            "style_guide": "..."
        }
    """
    if not conference_rule_id:
        return {}

    rule = db.query(ConferenceRule).filter(
        ConferenceRule.rule_id == conference_rule_id
    ).first()

    if not rule:
        return {}

    return {
        "name": rule.name,
        "format_rules": rule.format_rules or {},
        "style_guide": rule.style_guide or ""
    }


def get_previous_feedback_context(db, paper: Paper) -> dict:
    """
    前回提出のフィードバックを取得（再提出の場合）

    Returns:
        {
            "parent_title": "前回の論文タイトル",
            "summary": "前回のフィードバック要約",
            "suggestions": ["改善提案1", ...],
            "typos": ["誤字1", ...]
        }
    """
    if not paper.parent_paper_id:
        return {}

    # 親論文を取得
    parent_paper = db.query(Paper).filter(
        Paper.paper_id == paper.parent_paper_id
    ).first()

    if not parent_paper:
        return {}

    # 親論文の最新バージョンのフィードバックを取得
    parent_version = db.query(Version).filter(
        Version.paper_id == parent_paper.paper_id
    ).order_by(Version.version_number.desc()).first()

    if not parent_version:
        return {}

    feedback = db.query(Feedback).filter(
        Feedback.version_id == parent_version.version_id
    ).first()

    if not feedback:
        return {}

    return {
        "parent_title": parent_paper.title,
        "summary": feedback.overall_summary or "",
        "suggestions": (feedback.comments_json or {}).get("suggestions", []),
        "typos": (feedback.comments_json or {}).get("typos", [])
    }


# ================== Prompt Builder (Phase 1-3) ==================

def build_analysis_prompt(
    paper_text: str,
    conference_context: dict,
    previous_feedback: dict
) -> str:
    """
    コンテキストを含む分析プロンプトを組み立て

    Args:
        paper_text: 解析済み論文テキスト
        conference_context: 学会ルールコンテキスト
        previous_feedback: 前回フィードバックコンテキスト

    Returns:
        組み立てられたプロンプト文字列
    """
    sections = []

    # ヘッダー
    sections.append("あなたは学術論文のレビューを行う専門家です。以下の論文を分析し、改善提案を行ってください。")
    sections.append("")

    # 学会ルールセクション（あれば）
    if conference_context:
        sections.append("=" * 50)
        sections.append("## 対象学会・投稿規定")
        sections.append(f"学会名: {conference_context.get('name', '不明')}")

        format_rules = conference_context.get("format_rules", {})
        if format_rules:
            sections.append("")
            sections.append("### フォーマット規定")
            for key, value in format_rules.items():
                sections.append(f"- {key}: {value}")

        style_guide = conference_context.get("style_guide", "")
        if style_guide:
            sections.append("")
            sections.append("### スタイルガイド")
            sections.append(style_guide)

        sections.append("")

    # 前回フィードバックセクション（あれば）
    if previous_feedback:
        sections.append("=" * 50)
        sections.append("## 前回提出時のフィードバック（参考情報）")
        sections.append(f"前回タイトル: {previous_feedback.get('parent_title', '不明')}")

        if previous_feedback.get("summary"):
            sections.append("")
            sections.append("### 前回の総評")
            sections.append(previous_feedback["summary"])

        if previous_feedback.get("suggestions"):
            sections.append("")
            sections.append("### 前回の改善提案（これらが反映されているか確認してください）")
            for i, suggestion in enumerate(previous_feedback["suggestions"], 1):
                sections.append(f"{i}. {suggestion}")

        sections.append("")
        sections.append("※ 上記の前回フィードバックを踏まえ、改善されている点と残っている課題を明確にしてください。")
        sections.append("")

    # 分析依頼
    sections.append("=" * 50)
    sections.append("## 分析内容")
    sections.append("1. 要約（summary）: 200文字程度で論文の概要を説明")
    sections.append("2. 誤字脱字（typos）: 検出された誤字脱字のリスト")
    sections.append("3. 改善提案（suggestions）: 論文を改善するための具体的な提案")

    if previous_feedback:
        sections.append("4. 前回からの改善点（improvements_from_previous）: 前回フィードバックに対する改善状況")

    sections.append("")
    sections.append("## 出力形式（JSON）")
    sections.append("{")
    sections.append('  "summary": "論文の要約...",')
    sections.append('  "typos": ["誤字1", "誤字2"],')
    sections.append('  "suggestions": ["提案1", "提案2", "提案3"]')
    if previous_feedback:
        sections.append('  "improvements_from_previous": ["改善点1", "改善点2"]')
    sections.append("}")
    sections.append("")

    # 論文テキスト
    sections.append("=" * 50)
    sections.append("## 論文テキスト")
    sections.append(paper_text[:10000])  # 最初の10000文字のみ
    sections.append("")
    sections.append("## 回答（JSON形式）")

    return "\n".join(sections)


# ================== Parser & LLM Calls ==================

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


def call_ollama(prompt: str, is_mock_extended: bool = False) -> dict:
    """
    Ollamaを呼び出してテキスト分析

    Args:
        prompt: 組み立て済みプロンプト
        is_mock_extended: 拡張MOCKモード（プロンプトを返す）

    Returns:
        分析結果のdict
    """
    # 拡張MOCKモード: プロンプト自体を返す（デバッグ用）
    if settings.mock_mode and is_mock_extended:
        print("Extended Mock mode: Returning assembled prompt...")
        time.sleep(1)
        return {
            "summary": "[MOCK MODE] プロンプト確認モード",
            "typos": [],
            "suggestions": ["以下に組み立てられたプロンプトを表示しています。"],
            "_debug_prompt": prompt,
            "_debug_prompt_length": len(prompt)
        }

    # 通常MOCKモード: デモデータを返す
    if settings.mock_mode:
        print("Mock mode: Returning demo data...")
        time.sleep(2)
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

    # 実際のOllama呼び出し
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
            "typos": [],
            "suggestions": ["AIの応答をJSONとしてパースできませんでした"]
        }


# ================== Task Processing ==================

def process_diagnosis_task(task_data: dict):
    """
    Process SYSTEM_DIAGNOSIS task (Debug mode only)
    Dynamically imports the diagnostic module from /app/tests/
    """
    print("=" * 50)
    print(" SYSTEM_DIAGNOSIS task received")
    print("=" * 50)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "worker_check",
            "/app/tests/worker_check.py"
        )
        if spec and spec.loader:
            worker_check = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker_check)
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


def process_task(task_id: int, task_data: Optional[dict] = None):
    """
    タスクを処理（Phase 1-3: RAG Pipeline対応版）

    フロー:
    1. InferenceTask を取得
    2. Version 経由で File（cache_path）を取得
    3. コンテキスト収集（学会ルール、前回フィードバック）
    4. Parser でテキスト抽出
    5. プロンプト組み立て
    6. Ollama で分析
    7. Feedback に結果を保存
    8. Paper/InferenceTask のステータスを更新
    """
    if settings.debug_mode:
        print(f"【デバッグ】タスク処理開始: Task ID={task_id}")
        if task_data:
            print(f"【デバッグ】タスクデータ: {task_data}")

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

        paper = version.paper

        # プライマリファイルを取得
        primary_file = db.query(File).filter(
            File.version_id == version.version_id,
            File.is_primary == True
        ).first()

        if not primary_file:
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
        publish_notification(task_id, "PARSING", "PDF解析中 (1/4)")

        # 3. コンテキスト収集（Phase 1-3）
        if settings.debug_mode:
            print(f"【デバッグ】コンテキスト収集開始...")

        # 学会ルールコンテキスト
        conference_context = get_conference_context(db, task.conference_rule_id)
        if settings.debug_mode and conference_context:
            print(f"【デバッグ】学会ルール取得: {conference_context.get('name', 'N/A')}")

        # 前回フィードバックコンテキスト
        previous_feedback = get_previous_feedback_context(db, paper) if paper else {}
        if settings.debug_mode and previous_feedback:
            print(f"【デバッグ】前回フィードバック取得: {previous_feedback.get('parent_title', 'N/A')}")

        # 4. Parserを呼び出してテキスト抽出
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

        # ステータス更新: RAG (コンテキスト処理中)
        task.status = TaskStatus.RAG
        db.commit()
        publish_notification(task_id, "RAG", "コンテキスト処理中 (2/4)")

        # 5. プロンプト組み立て（Phase 1-3）
        if settings.debug_mode:
            print(f"【デバッグ】プロンプト組み立て中...")

        prompt = build_analysis_prompt(
            paper_text=parsed_text,
            conference_context=conference_context,
            previous_feedback=previous_feedback
        )

        if settings.debug_mode:
            print(f"【デバッグ】プロンプト長: {len(prompt)}文字")

        # ステータス更新: LLM
        task.status = TaskStatus.LLM
        db.commit()
        publish_notification(task_id, "LLM", "AI分析中 (3/4)")

        # 6. Ollamaを呼び出して分析
        if settings.debug_mode:
            print(f"【デバッグ】AI推論(Ollama)を開始します...")
        print("Calling Ollama for analysis...")

        # 拡張MOCKモード判定（デバッグモード + タスクデータにdebug_promptフラグ）
        is_mock_extended = (
            settings.mock_mode and
            settings.debug_mode and
            task_data and
            task_data.get("debug_prompt", False)
        )

        result = call_ollama(prompt, is_mock_extended=is_mock_extended)
        if settings.debug_mode:
            print(f"【デバッグ】AI推論完了。結果をDBに書き込みます。")
        print("Ollama analysis complete")

        # 7. Feedback に結果を保存
        comments = {
            "typos": result.get("typos", []),
            "suggestions": result.get("suggestions", [])
        }

        # 前回からの改善点があれば追加
        if "improvements_from_previous" in result:
            comments["improvements_from_previous"] = result["improvements_from_previous"]

        # 拡張MOCKモードの場合、プロンプトデバッグ情報を追加
        if "_debug_prompt" in result:
            comments["_debug_prompt"] = result["_debug_prompt"]
            comments["_debug_prompt_length"] = result["_debug_prompt_length"]

        feedback = Feedback(
            version_id=version.version_id,
            task_id=task.task_id,
            score_json=None,  # 将来的にスコア計算を実装
            comments_json=comments,
            overall_summary=result.get("summary", "")
        )
        db.add(feedback)

        # 8. ステータス更新: COMPLETED
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()

        if paper:
            paper.status = PaperStatus.COMPLETED

        db.commit()
        publish_notification(task_id, "COMPLETED", "分析完了 (4/4)")
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        db.rollback()

        try:
            task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
            if task:
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()

                if task.version and task.version.paper:
                    task.version.paper.status = PaperStatus.ERROR

                db.commit()
                publish_notification(task_id, "ERROR", error_message=str(e))
        except Exception as inner_e:
            print(f"Failed to update error status: {inner_e}")

    finally:
        db.close()


def parse_task_data(data: bytes) -> tuple:
    """
    Parse task data from Redis.
    Returns: (task_type, task_data)
    - For regular tasks: ("REGULAR", {"task_id": int, "job_type": str, ...})
    - For reference tasks: ("REFERENCE_ONLY", {"task_id": int, "job_type": str})
    - For diagnosis tasks: ("SYSTEM_DIAGNOSIS", task_data as dict)
    - Legacy format (task_id only): ("REGULAR", {"task_id": int, "job_type": "ANALYSIS"})
    """
    try:
        decoded = data.decode("utf-8")

        try:
            task_data = json.loads(decoded)
            if isinstance(task_data, dict):
                if task_data.get("type") == "SYSTEM_DIAGNOSIS":
                    return ("SYSTEM_DIAGNOSIS", task_data)
                if "task_id" in task_data:
                    job_type = task_data.get("job_type", "ANALYSIS")
                    if job_type == "REFERENCE_ONLY":
                        return ("REFERENCE_ONLY", task_data)
                    return ("REGULAR", task_data)
        except json.JSONDecodeError:
            pass

        task_id = int(decoded)
        return ("REGULAR", {"task_id": task_id, "job_type": "ANALYSIS"})

    except Exception as e:
        print(f"Error parsing task data: {e}")
        return (None, None)


def main():
    """Main worker loop."""
    print("=" * 50)
    print(" NAK-BASE AI INFERENCE WORKER")
    print(" Phase 1-3: RAG Pipeline + Context-Aware Prompt")
    print("=" * 50)
    print(f"Redis: {settings.redis_url}")
    print(f"Ollama: {settings.ollama_url}")
    print(f"Parser: {settings.parser_url}")
    print(f"Debug Mode: {settings.debug_mode}")
    print(f"Mock Mode: {settings.mock_mode}")

    client = get_redis_client()

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
            result = client.blpop(TASK_QUEUE, timeout=30)

            if result:
                _, data = result
                task_type, task_data = parse_task_data(data)

                if task_type == "SYSTEM_DIAGNOSIS":
                    print(f"Received SYSTEM_DIAGNOSIS task")
                    process_diagnosis_task(task_data)

                elif task_type == "REFERENCE_ONLY":
                    task_id = task_data.get("task_id")
                    print(f"Received REFERENCE_ONLY task: {task_id} (skipping analysis)")

                elif task_type == "REGULAR":
                    task_id = task_data.get("task_id")
                    job_type = task_data.get("job_type", "ANALYSIS")
                    conference_id = task_data.get("conference_id")
                    parent_paper_id = task_data.get("parent_paper_id")
                    print(f"Received regular task: {task_id} (job_type: {job_type}, conference: {conference_id}, parent: {parent_paper_id})")
                    process_task(task_id, task_data)

                else:
                    print(f"Unknown task type, skipping: {data}")

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

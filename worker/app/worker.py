"""
nak-base AI Inference Worker (Refactored)
- タスクのオーケストレーションを担当
- 外部API通信は services/clients に分離
"""
import redis
import time
import json
import difflib
from datetime import datetime
from typing import Optional, List

from sqlalchemy import text

from .config import get_settings
from .database import get_db_session
from .models import (
    InferenceTask, File, Feedback, Paper, Version,
    TaskStatus, PaperStatus, ConferenceRule, Embedding
)
from .services.ollama_client import generate_embedding
from .services.parser_client import call_parser
from .orchestrator import run_agents, merge_results

settings = get_settings()

TASK_QUEUE = "tasks"
NOTIFICATION_CHANNEL = "task_notifications"


def publish_notification(
    task_id: int,
    status: str,
    phase: str | None = None,
    error_message: str | None = None,
    agent: str | None = None,
):
    """タスク通知をRedis Pub/Subに発行（マルチエージェント対応）"""
    try:
        client = get_redis_client()
        notification = {
            "task_id": task_id,
            "status": status,
            "phase": phase,
            "error_message": error_message,
            "agent": agent,
        }
        client.publish(NOTIFICATION_CHANNEL, json.dumps(notification))
        if settings.debug_mode:
            print(f"【デバッグ】通知発行: {notification}")
    except Exception as e:
        print(f"Failed to publish notification: {e}")


def get_redis_client():
    return redis.from_url(settings.redis_url)


# ================== Data Access & Logic ==================

def save_chunk_embeddings(db, file_id: int, chunks: List[dict]) -> int:
    """パース結果のチャンクをEmbeddingテーブルに保存"""
    saved_count = 0
    for chunk in chunks:
        content = chunk.get("content", "")
        if not content.strip():
            continue

        embedding_vector = generate_embedding(content)

        raw_section_title = chunk.get("section_title")
        section_title = (raw_section_title[:250] + "...") if raw_section_title and len(raw_section_title) > 255 else raw_section_title

        embedding_record = Embedding(
            file_id=file_id,
            chunk_index=chunk.get("chunk_index", saved_count),
            section_title=section_title,
            page_number=chunk.get("page_number"),
            line_number=chunk.get("line_number"),
            content_chunk=content,
            location_json=chunk.get("location_json"),
            embedding=embedding_vector
        )
        db.add(embedding_record)
        saved_count += 1

    db.commit()
    return saved_count


def semantic_search_chunks(db, query_text: str, exclude_file_id: Optional[int] = None, top_k: int = 5) -> List[dict]:
    """コサイン類似度によるセマンティック検索"""
    query_embedding = generate_embedding(query_text)
    query = text("""
        SELECT e.content_chunk, e.section_title, e.page_number, f.original_filename, p.title as paper_title, 1 - (e.embedding <=> :query_vector) as similarity
        FROM embeddings e
        JOIN files f ON e.file_id = f.file_id
        JOIN versions v ON f.version_id = v.version_id
        JOIN papers p ON v.paper_id = p.paper_id
        WHERE e.embedding IS NOT NULL AND (:exclude_file_id IS NULL OR e.file_id != :exclude_file_id)
        ORDER BY e.embedding <=> :query_vector
        LIMIT :top_k
    """)
    results = db.execute(query, {"query_vector": str(query_embedding), "exclude_file_id": exclude_file_id, "top_k": top_k}).fetchall()
    return [{"content": row[0], "section": row[1], "page_number": row[2], "filename": row[3], "paper_title": row[4], "similarity": float(row[5]) if row[5] else 0.0} for row in results]


def get_parent_paper_text(db, paper: Paper) -> str:
    """前回（親）論文の全文テキストを取得"""
    if not paper.parent_paper_id:
        return ""
    try:
        parent_paper = db.query(Paper).filter(Paper.paper_id == paper.parent_paper_id).first()
        if not parent_paper: return ""
        parent_version = db.query(Version).filter(Version.paper_id == parent_paper.paper_id).order_by(Version.version_number.desc()).first()
        if not parent_version: return ""
        parent_file = db.query(File).filter(File.version_id == parent_version.version_id, File.is_primary == True).first() or db.query(File).filter(File.version_id == parent_version.version_id).first()
        if not parent_file or not parent_file.cache_path: return ""
        
        if settings.debug_mode: print(f"【デバッグ】親論文をパース中: {parent_file.cache_path}")
        parse_result = call_parser(parent_file.cache_path)
        parent_text = parse_result.get("text", "")
        if settings.debug_mode: print(f"【デバッグ】親論文テキスト取得完了: {len(parent_text)}文字")
        return parent_text
    except Exception as e:
        print(f"Warning: Failed to get parent paper text: {e}")
        return ""


def generate_diff_summary(old_text: str, new_text: str, max_length: int = 3000) -> str:
    """2つのテキスト間の差分サマリーを生成"""
    if not old_text or not new_text: return ""
    diff = difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True), fromfile='前回の論文', tofile='今回の論文', lineterm='')
    diff_lines = [line for line in diff if line.startswith(('---', '+++', '@@', '+', '-'))]
    if not diff_lines: return ""
    diff_text = '\n'.join(diff_lines)
    return diff_text[:max_length] + "\n\n... (以下省略)" if len(diff_text) > max_length else diff_text


# ================== Context Gathering ==================

def get_full_context(db, task: InferenceTask, paper_text: str, primary_file_id: int) -> dict:
    """RAG、前回FB、差分など、すべてのコンテキストを収集する"""
    paper = task.version.paper
    
    # 学会ルール
    conference_rule = db.query(ConferenceRule).filter(ConferenceRule.rule_id == task.conference_rule_id).first()
    conference_context = {
        "name": conference_rule.name,
        "format_rules": conference_rule.format_rules or {},
        "style_guide": conference_rule.style_guide or ""
    } if conference_rule else {}

    # 前回フィードバック
    previous_feedback = {}
    if paper and paper.parent_paper_id:
        parent_paper = db.query(Paper).filter(Paper.paper_id == paper.parent_paper_id).first()
        if parent_paper:
            parent_version = db.query(Version).filter(Version.paper_id == parent_paper.paper_id).order_by(Version.version_number.desc()).first()
            if parent_version:
                feedback = db.query(Feedback).filter(Feedback.version_id == parent_version.version_id).first()
                if feedback:
                    previous_feedback = {
                        "parent_title": parent_paper.title,
                        "summary": feedback.overall_summary or "",
                        "suggestions": (feedback.comments_json or {}).get("suggestions", []),
                        "typos": (feedback.comments_json or {}).get("typos", [])
                    }

    # RAGコンテキスト
    query_text = paper_text[:2000]
    rag_context = {
        "related_chunks": semantic_search_chunks(db, query_text, exclude_file_id=primary_file_id, top_k=settings.rag_top_k),
        "related_rules": [] # Placeholder for now
    }

    # 差分
    diff_text = ""
    if paper and paper.parent_paper_id:
        parent_text = get_parent_paper_text(db, paper)
        if parent_text:
            diff_text = generate_diff_summary(parent_text, paper_text)

    return {
        "conference_context": conference_context,
        "previous_feedback": previous_feedback,
        "rag_context": rag_context,
        "diff_text": diff_text
    }


# ================== Task Processing ==================

def process_task(task_id, task_data: Optional[dict] = None):
    """タスクを処理するメイン関数"""
    if settings.debug_mode:
        print(f"【デバッグ】タスク処理開始: Task ID={task_id}, Data={task_data}")

    # SYSTEM_DIAGNOSIS タスクは通常の推論フローには流さず、診断モジュールに委譲する
    if task_data and task_data.get("type") == "SYSTEM_DIAGNOSIS":
        if not settings.debug_mode:
            print(f"Skipping SYSTEM_DIAGNOSIS task {task_id} (debug_mode=False)")
            return
        try:
            from tests.worker_check import run_worker_diagnosis
            run_worker_diagnosis(task_data)
        except ImportError as e:
            print(f"Diagnosis module not available: {e}")
        except Exception as e:
            print(f"Diagnosis task {task_id} failed: {e}")
        return

    db = get_db_session()
    try:
        task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
        if not task:
            print(f"Task {task_id} not found")
            return

        version = task.version
        primary_file = db.query(File).filter(File.version_id == version.version_id, File.is_primary == True).first() or db.query(File).filter(File.version_id == version.version_id).first()

        if not primary_file or not primary_file.cache_path:
            raise ValueError(f"No primary file found for version {version.version_id}")

        # --- 1. PARSING ---
        task.status, task.started_at = TaskStatus.PARSING, datetime.utcnow()
        db.commit()
        publish_notification(task_id, "PARSING", "PDF解析中 (1/4)")
        
        parse_result = call_parser(primary_file.cache_path)
        parsed_text, chunks = parse_result["text"], parse_result.get("chunks", [])
        if settings.debug_mode: print(f"【デバッグ】Parser完了: {len(parsed_text)}文字, {len(chunks)}チャンク")

        # --- 2. RAG (Embedding & Context Gathering) ---
        task.status = TaskStatus.RAG
        db.commit()
        publish_notification(task_id, "RAG", "Embedding生成・検索中 (2/4)")

        if chunks:
            saved_count = save_chunk_embeddings(db, primary_file.file_id, chunks)
            if settings.debug_mode: print(f"【デバッグ】Embedding保存完了: {saved_count}件")
        
        context = get_full_context(db, task, parsed_text, primary_file.file_id)
        # エージェントへ渡す共通コンテキストへ paper_text を含める
        context["paper_text"] = parsed_text

        # --- 3. LLM (マルチエージェント・パイプライン) ---
        task.status = TaskStatus.LLM
        db.commit()
        publish_notification(task_id, "LLM", "マルチエージェント解析中 (3/4)")

        def _agent_notify(agent_name: str, label: str):
            publish_notification(task_id, "LLM", label, agent=agent_name)

        agent_results = run_agents(context, notify=_agent_notify)
        merged = merge_results(agent_results)
        if settings.debug_mode:
            print(f"【デバッグ】Agent meta: {merged.get('agent_meta')}")
        print("Multi-agent analysis complete")

        # --- 4. SAVE FEEDBACK ---
        feedback = Feedback(
            version_id=version.version_id,
            task_id=task.task_id,
            comments_json={
                "typos": merged.get("typos", []),
                "suggestions": merged.get("suggestions", []),
                "improvements_from_previous": merged.get("improvements_from_previous", []),
                "agents": merged.get("agents", {}),
                "agent_meta": merged.get("agent_meta", {}),
            },
            overall_summary=merged.get("summary", "")
        )
        db.add(feedback)

        # --- 5. COMPLETE ---
        task.status, task.completed_at = TaskStatus.COMPLETED, datetime.utcnow()
        if version.paper: version.paper.status = PaperStatus.COMPLETED
        db.commit()
        publish_notification(task_id, "COMPLETED", "分析完了 (4/4)")
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        try:
            task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
            if task:
                task.status, task.error_message, task.completed_at = TaskStatus.ERROR, str(e), datetime.utcnow()
                if task.version and task.version.paper: task.version.paper.status = PaperStatus.ERROR
                db.commit()
                publish_notification(task_id, "ERROR", error_message=str(e))
        except Exception as inner_e:
            print(f"Failed to update error status: {inner_e}")
    finally:
        db.close()


def parse_task_data(data: bytes) -> tuple:
    """Parse task data from Redis."""
    try:
        task_data = json.loads(data.decode("utf-8"))
        task_id = task_data.get("task_id")
        return task_id, task_data
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Fallback for simple integer task_id
        return int(data.decode("utf-8")), {}
    except Exception as e:
        print(f"Error parsing task data: {e}")
        return None, None


def main():
    """Main worker loop."""
    print("=" * 50)
    print(" NAK-BASE AI INFERENCE WORKER (Multi-Agent Pipeline)")
    print(f"  Mode: {'Mock' if settings.mock_mode else 'Live'}, Debug: {settings.debug_mode}")
    print(f"  Ollama: {settings.ollama_url}, Parser: {settings.parser_url}")
    print(f"  LLM Provider: {settings.llm_provider}, "
          f"fast={settings.model_for(use_pro=False)}, pro={settings.model_for(use_pro=True)}")
    print(f"  Agents: parallel={settings.agents_parallel}, timeout={settings.agent_timeout}s")
    print("=" * 50)

    client = get_redis_client()
    while True:
        try:
            client.ping()
            print("Connected to Redis. Waiting for tasks...")
            break
        except redis.ConnectionError:
            print("Waiting for Redis...")
            time.sleep(2)

    while True:
        try:
            result = client.blpop(TASK_QUEUE, timeout=30)
            if result:
                _, data = result
                task_id, task_data = parse_task_data(data)
                if task_id:
                    print(f"Received task: {task_id}")
                    process_task(task_id, task_data)
        except Exception as e:
            print(f"Worker loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

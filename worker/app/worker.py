"""
AI Inference Worker
Processes paper analysis tasks from Redis queue
"""
import redis
import json
import time
import io
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
import google.generativeai as genai

from .config import get_settings
from .database import get_db_session, Base, engine
from .agents.parser import extract_text_from_pdf, extract_text_from_tex, extract_abstract_and_conclusion
from .agents.linter import run_linter_agent
from .agents.logic import run_logic_agent
from .agents.rag import run_rag_agent
from .agents.diff_checker import run_diff_checker

# Google Drive imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

settings = get_settings()

INFERENCE_QUEUE = "inference_tasks"


# Define models locally to avoid import issues
class Version(Base):
    __tablename__ = "versions"
    version_id = Column(Integer, primary_key=True)
    paper_id = Column(Integer)
    drive_file_id = Column(String(255))
    version_number = Column(Integer)
    file_name = Column(String(500))
    file_type = Column(String(10))


class Paper(Base):
    __tablename__ = "papers"
    paper_id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    title = Column(String(500))
    status = Column(String(20))


class Feedback(Base):
    __tablename__ = "feedbacks"
    feedback_id = Column(Integer, primary_key=True)
    version_id = Column(Integer)
    report_drive_id = Column(String(255))
    score_json = Column(JSONB)
    comments_json = Column(JSONB)
    overall_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class InferenceTask(Base):
    __tablename__ = "inference_tasks"
    task_id = Column(Integer, primary_key=True)
    version_id = Column(Integer)
    status = Column(String(20))
    error_message = Column(Text)
    conference_rule_id = Column(String(50))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class ConferenceRule(Base):
    __tablename__ = "conference_rules"
    rule_id = Column(String(50), primary_key=True)
    name = Column(String(255))
    format_rules = Column(JSONB)
    style_guide = Column(Text)


def get_redis_client():
    return redis.from_url(settings.redis_url)


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)


def download_file_from_drive(file_id: str) -> bytes:
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    file_content = io.BytesIO()
    downloader = MediaIoBaseDownload(file_content, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return file_content.getvalue()


def get_previous_feedback(db: Session, paper_id: int, current_version_number: int) -> dict | None:
    """Get feedback from the previous version."""
    prev_version = db.query(Version).filter(
        Version.paper_id == paper_id,
        Version.version_number == current_version_number - 1
    ).first()

    if not prev_version:
        return None

    feedback = db.query(Feedback).filter(
        Feedback.version_id == prev_version.version_id
    ).first()

    if feedback:
        return {
            "score_json": feedback.score_json,
            "comments_json": feedback.comments_json,
            "linter_result": feedback.comments_json.get("linter_result") if feedback.comments_json else None,
            "logic_result": feedback.comments_json.get("logic_result") if feedback.comments_json else None
        }

    return None


def process_task(task_data: dict):
    """Process a single inference task."""
    db = get_db_session()

    task_id = task_data["task_id"]
    version_id = task_data["version_id"]
    paper_id = task_data["paper_id"]
    file_id = task_data["file_id"]
    conference_rule_id = task_data.get("conference_rule_id", "GENERAL")

    print(f"Processing task {task_id} for version {version_id}")

    try:
        # Update task status
        task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
        if task:
            task.status = "Processing"
            task.started_at = datetime.utcnow()
            db.commit()

        # Get version info
        version = db.query(Version).filter(Version.version_id == version_id).first()
        if not version:
            raise Exception("Version not found")

        # Get paper info
        paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
        if not paper:
            raise Exception("Paper not found")

        # Get conference rules
        conf_rule = db.query(ConferenceRule).filter(
            ConferenceRule.rule_id == conference_rule_id
        ).first()
        format_rules = conf_rule.format_rules if conf_rule else {}

        # Download file from Drive
        print(f"Downloading file {file_id} from Drive...")
        file_content = download_file_from_drive(file_id)

        # Parse document
        print("Parsing document...")
        if version.file_type == 'pdf':
            parsed_doc = extract_text_from_pdf(file_content)
        else:
            parsed_doc = extract_text_from_tex(file_content)

        abstract_conclusion = extract_abstract_and_conclusion(parsed_doc)

        # Initialize Gemini
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        paper_text = parsed_doc.get("full_text", "")

        # Get previous feedback for diff checking
        prev_feedback = get_previous_feedback(db, paper_id, version.version_number)

        # Run agents
        print("Running Linter Agent...")
        linter_result = run_linter_agent(model, paper_text, format_rules)

        print("Running Logic Agent...")
        logic_result = run_logic_agent(
            model,
            parsed_doc,
            abstract_conclusion.get("abstract", ""),
            abstract_conclusion.get("conclusion", "")
        )

        print("Running RAG Agent...")
        rag_result = run_rag_agent(model, db, paper_text, paper.title)

        print("Running Diff Checker...")
        diff_result = run_diff_checker(model, paper_text, prev_feedback)

        # Calculate overall scores
        linter_score = linter_result.get("overall_score", 70)
        logic_score = logic_result.get("overall_logic_score", 70)
        novelty_score = rag_result.get("novelty_assessment", {}).get("score", 70)

        overall_score = (linter_score + logic_score + novelty_score) / 3

        score_json = {
            "overall": round(overall_score),
            "format": linter_score,
            "logic": logic_score,
            "novelty": novelty_score,
            "improvement": diff_result.get("improvement_score")
        }

        comments_json = {
            "linter_result": linter_result,
            "logic_result": logic_result,
            "rag_result": rag_result,
            "diff_result": diff_result
        }

        # Generate overall summary
        summary = f"""
論文「{paper.title}」の分析結果:

【総合スコア: {round(overall_score)}/100】

■ 形式面 ({linter_score}/100):
- 誤字脱字: {len(linter_result.get('typos', []))}件検出
- フォーマット問題: {len(linter_result.get('format_issues', []))}件検出

■ 論理構造 ({logic_score}/100):
{logic_result.get('summary', '分析完了')}

■ 新規性 ({novelty_score}/100):
{rag_result.get('novelty_assessment', {}).get('explanation', '分析完了')}

{'■ 前回からの改善:' if diff_result.get('improvement_score') else ''}
{diff_result.get('summary', '') if diff_result.get('improvement_score') else ''}
        """.strip()

        # Save feedback
        feedback = Feedback(
            version_id=version_id,
            score_json=score_json,
            comments_json=comments_json,
            overall_summary=summary
        )
        db.add(feedback)

        # Update task and paper status
        task.status = "Completed"
        task.completed_at = datetime.utcnow()
        paper.status = "Completed"

        db.commit()
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        db.rollback()

        # Update task with error
        task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
        if task:
            task.status = "Error"
            task.error_message = str(e)
            task.completed_at = datetime.utcnow()

        # Update paper status
        paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
        if paper:
            paper.status = "Error"

        db.commit()

    finally:
        db.close()


def main():
    """Main worker loop."""
    print("Starting AI Inference Worker...")
    print(f"Connecting to Redis: {settings.redis_url}")

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
            # Blocking pop from queue
            result = client.blpop(INFERENCE_QUEUE, timeout=30)

            if result:
                _, data = result
                task_data = json.loads(data)
                print(f"Received task: {task_data}")
                process_task(task_data)
            else:
                # Timeout, continue waiting
                pass

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

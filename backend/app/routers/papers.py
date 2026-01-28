"""
Phase 1 論文ルーター
新スキーマ対応: Paper -> Version -> File -> InferenceTask
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
import hashlib

from ..database import get_db
from ..models import Paper, Version, File as FileModel, InferenceTask, Feedback
from ..schemas import (
    PaperResponse, PaperWithVersions, PaperWithDetails,
    VersionResponse, VersionWithDetails,
    FileResponse, InferenceTaskResponse, FeedbackResponse,
    UploadResponse
)
from ..services.queue_service import push_task
from ..config import get_settings

router = APIRouter(prefix="/papers", tags=["papers"])
settings = get_settings()


@router.get("/", response_model=List[PaperResponse])
def list_papers(db: Session = Depends(get_db)):
    """論文一覧を取得（削除されていないもののみ）"""
    papers = db.query(Paper).filter(Paper.is_deleted == False).order_by(Paper.created_at.desc()).all()
    return papers


@router.get("/{paper_id}", response_model=PaperWithDetails)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """論文詳細を取得（バージョン・ファイル・タスク・フィードバック含む）"""
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.is_deleted == False).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    title: str = Form(...),
    file: UploadFile = File(...),
    target_conference: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    論文をアップロード

    Phase 1 フロー:
    1. PDFファイルをローカルボリュームに保存
    2. Paper レコード作成
    3. Version レコード作成（version_number=1）
    4. File レコード作成（ファイルパス保存）
    5. InferenceTask レコード作成（status=pending）
    6. Redis に task_id を PUSH
    """
    if settings.debug_mode:
        print(f"[DEBUG] Upload received: title='{title}', file='{file.filename}'")

    # PDFのみ受付
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # ファイル保存（UUIDで一意なファイル名）
    file_uuid = str(uuid.uuid4())
    file_name = f"{file_uuid}.pdf"
    file_path = os.path.join(settings.storage_path, file_name)

    # ストレージディレクトリ確認
    os.makedirs(settings.storage_path, exist_ok=True)

    # ファイル保存 + ハッシュ計算
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    with open(file_path, "wb") as f:
        f.write(content)

    if settings.debug_mode:
        print(f"[DEBUG] File saved: {file_path} (hash: {file_hash[:16]}...)")

    # Paper 作成
    paper = Paper(
        user_id=1,  # 固定デモユーザー（Phase 1）
        title=title,
        target_conference=target_conference,
        status="processing"
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    # Version 作成
    version = Version(
        paper_id=paper.id,
        version_number=1
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    # File 作成
    file_record = FileModel(
        version_id=version.id,
        file_path=file_path,
        file_type="pdf",
        original_filename=file.filename,
        file_hash=file_hash
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    # InferenceTask 作成
    task = InferenceTask(
        version_id=version.id,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if settings.debug_mode:
        print(f"[DEBUG] DB records created: Paper={paper.id}, Version={version.id}, File={file_record.id}, Task={task.id}")

    # Redis にタスク追加
    push_task(task.id)

    if settings.debug_mode:
        print(f"[DEBUG] Task {task.id} pushed to Redis queue")

    return UploadResponse(
        message="Upload successful",
        paper_id=paper.id,
        version_id=version.id,
        file_id=file_record.id,
        task_id=task.id
    )


@router.get("/versions/{version_id}", response_model=VersionWithDetails)
def get_version(version_id: int, db: Session = Depends(get_db)):
    """バージョン詳細を取得"""
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.get("/tasks/{task_id}", response_model=InferenceTaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """タスク詳細を取得（ステータス確認用）"""
    task = db.query(InferenceTask).filter(InferenceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/feedbacks/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    """フィードバック詳細を取得"""
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@router.get("/versions/{version_id}/feedbacks", response_model=List[FeedbackResponse])
def get_version_feedbacks(version_id: int, db: Session = Depends(get_db)):
    """バージョンに紐づくフィードバック一覧を取得"""
    feedbacks = db.query(Feedback).filter(Feedback.version_id == version_id).all()
    return feedbacks


@router.delete("/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """論文を論理削除"""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    paper.is_deleted = True
    db.commit()

    return {"message": "Paper deleted", "paper_id": paper_id}

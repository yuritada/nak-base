"""
MVP版 論文ルーター
シンプルなアップロード・一覧・詳細取得
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import os
import uuid

from ..database import get_db
from ..models import Paper, Task
from ..schemas import PaperResponse, PaperWithTasks, TaskResponse, UploadResponse
from ..services.queue_service import push_task
from ..config import get_settings

router = APIRouter(prefix="/papers", tags=["papers"])
settings = get_settings()


@router.get("/", response_model=List[PaperResponse])
def list_papers(db: Session = Depends(get_db)):
    """論文一覧を取得（3秒ポーリング用）"""
    papers = db.query(Paper).order_by(Paper.created_at.desc()).all()
    return papers


@router.get("/{paper_id}", response_model=PaperWithTasks)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """論文詳細を取得（タスク含む）"""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    論文をアップロード

    1. PDFファイルをローカルボリュームに保存
    2. papersレコード作成
    3. tasksレコード作成（status=pending）
    4. Redisにtask_idをPUSH
    """
    if settings.debug_mode:
        print(f"【デバッグ】論文アップロード受信: タイトル='{title}', ファイル='{file.filename}'")

    # PDFのみ受付
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # ファイル保存（UUIDで一意なファイル名）
    file_uuid = str(uuid.uuid4())
    file_name = f"{file_uuid}.pdf"
    file_path = os.path.join(settings.storage_path, file_name)

    # ストレージディレクトリ確認
    os.makedirs(settings.storage_path, exist_ok=True)

    # ファイル保存
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if settings.debug_mode:
        print(f"【デバッグ】ローカルストレージに保存完了: {file_path}")

    # Paper作成
    paper = Paper(
        user_id=1,  # 固定デモユーザー
        title=title
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    # Task作成
    task = Task(
        paper_id=paper.id,
        file_path=file_path,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if settings.debug_mode:
        print(f"【デバッグ】DB登録完了: Paper ID={paper.id}, Task ID={task.id}")

    # Redisにタスク追加
    push_task(task.id)

    if settings.debug_mode:
        print(f"【デバッグ】RedisキューにTask ID={task.id}を投入しました")

    return UploadResponse(
        message="Upload successful",
        paper_id=paper.id,
        task_id=task.id
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """タスク詳細を取得（結果確認用）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

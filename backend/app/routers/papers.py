"""
論文ルーター
Phase 1.5: SSE対応・参照モード対応
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
import os
import uuid

from ..database import get_db
from ..models import Paper, Version, File as FileModel, InferenceTask, Feedback, PaperStatus, TaskStatus, FileRole
from ..schemas import (
    PaperResponse, PaperDetail, PaperListItem,
    VersionResponse, InferenceTaskResponse, UploadResponse, FeedbackResponse
)
from ..services.queue_service import push_task_with_payload
from ..config import get_settings

router = APIRouter(prefix="/papers", tags=["papers"])
settings = get_settings()


def get_task_phase_text(status: TaskStatus) -> str:
    """タスクステータスからフロントエンド表示用のフェーズ文字列を生成"""
    phase_map = {
        TaskStatus.PENDING: "待機中",
        TaskStatus.PARSING: "PDF解析中 (1/3)",
        TaskStatus.RAG: "RAG処理中 (2/3)",
        TaskStatus.LLM: "AI分析中 (3/3)",
        TaskStatus.COMPLETED: "完了",
        TaskStatus.ERROR: "エラー",
    }
    return phase_map.get(status, "不明")


@router.get("/", response_model=List[PaperListItem])
def list_papers(db: Session = Depends(get_db)):
    """
    論文一覧を取得（削除されていないもののみ）

    最新バージョンのタスク情報を含むフラットなレスポンスを返す
    """
    papers = db.query(Paper).filter(Paper.is_deleted == False).order_by(Paper.created_at.desc()).all()

    result = []
    for paper in papers:
        # 最新バージョンを取得
        latest_version = db.query(Version).filter(
            Version.paper_id == paper.paper_id
        ).order_by(desc(Version.version_number)).first()

        latest_task = None
        if latest_version:
            # 最新バージョンの最新タスクを取得
            latest_task = db.query(InferenceTask).filter(
                InferenceTask.version_id == latest_version.version_id
            ).order_by(desc(InferenceTask.created_at)).first()

        item = PaperListItem(
            paper_id=paper.paper_id,
            owner_id=paper.owner_id,
            title=paper.title,
            status=paper.status,
            created_at=paper.created_at,
            latest_task_id=latest_task.task_id if latest_task else None,
            latest_task_status=latest_task.status if latest_task else None,
            phase=get_task_phase_text(latest_task.status) if latest_task else None,
        )
        result.append(item)

    return result


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    """論文詳細を取得（バージョンとファイル含む）"""
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.is_deleted == False).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/{paper_id}/versions", response_model=List[VersionResponse])
def list_versions(paper_id: int, db: Session = Depends(get_db)):
    """論文のバージョン一覧を取得"""
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    versions = db.query(Version).filter(Version.paper_id == paper_id).order_by(Version.version_number.desc()).all()
    return versions


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    title: str = Form(...),
    file: UploadFile = File(...),
    is_reference: Optional[bool] = Form(False),
    db: Session = Depends(get_db)
):
    """
    論文をアップロード

    Args:
        title: 論文タイトル
        file: アップロードファイル（PDF, ZIP, TeX）
        is_reference: 参考論文フラグ（True=解析スキップ）

    フロー:
    1. ファイルをローカルボリュームに保存
    2. Paper レコード作成
    3. Version レコード作成 (version_number=1)
    4. File レコード作成
    5. InferenceTask レコード作成 (status=Pending)
    6. Redisにタスクを投入（job_typeを含む）
    """
    if settings.debug_mode:
        print(f"【デバッグ】論文アップロード受信: タイトル='{title}', ファイル='{file.filename}', is_reference={is_reference}")

    # PDF, ZIP, TeX, DOCXを受付
    lower_filename = file.filename.lower()
    allowed_extensions = ('.pdf', '.zip', '.tex', '.docx')
    if not any(lower_filename.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF, ZIP, TeX, and DOCX files are accepted. Got: {file.filename}"
        )

    # ファイル拡張子を取得してFileRoleを決定
    if lower_filename.endswith('.pdf'):
        file_ext = '.pdf'
        file_role = FileRole.MAIN_PDF
    elif lower_filename.endswith('.docx'):
        file_ext = '.docx'
        file_role = FileRole.MAIN_DOCX
    elif lower_filename.endswith('.zip'):
        file_ext = '.zip'
        file_role = FileRole.SOURCE_TEX
    else:  # .tex
        file_ext = '.tex'
        file_role = FileRole.SOURCE_TEX

    # ファイル保存（UUIDで一意なファイル名）
    file_uuid = str(uuid.uuid4())
    file_name = f"{file_uuid}{file_ext}"
    file_path = os.path.join(settings.storage_path, file_name)

    # ストレージディレクトリ確認
    os.makedirs(settings.storage_path, exist_ok=True)

    # ファイル保存
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if settings.debug_mode:
        print(f"【デバッグ】ローカルストレージに保存完了: {file_path}")

    # 1. Paper作成
    # 参考論文の場合は最初からCOMPLETEDステータス
    initial_status = PaperStatus.COMPLETED if is_reference else PaperStatus.PROCESSING

    paper = Paper(
        owner_id=1,  # デモユーザー（Phase 2でOAuth実装時に変更）
        title=title,
        status=initial_status
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    if settings.debug_mode:
        print(f"【デバッグ】Paper作成: paper_id={paper.paper_id}")

    # 2. Version作成
    version = Version(
        paper_id=paper.paper_id,
        version_number=1
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    if settings.debug_mode:
        print(f"【デバッグ】Version作成: version_id={version.version_id}")

    # 3. File作成
    file_record = FileModel(
        version_id=version.version_id,
        file_role=file_role,
        is_primary=True,
        cache_path=file_path,
        is_cached=True,
        original_filename=file.filename
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    if settings.debug_mode:
        print(f"【デバッグ】File作成: file_id={file_record.file_id}")

    # 4. InferenceTask作成
    # 参考論文の場合はCOMPLETEDステータスで作成（解析スキップ）
    initial_task_status = TaskStatus.COMPLETED if is_reference else TaskStatus.PENDING

    task = InferenceTask(
        version_id=version.version_id,
        status=initial_task_status
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if settings.debug_mode:
        print(f"【デバッグ】InferenceTask作成: task_id={task.task_id}, status={initial_task_status}")

    # 5. Redisにタスク追加（参考論文でない場合のみ）
    if not is_reference:
        job_type = "ANALYSIS"
        push_task_with_payload(task.task_id, job_type)

        if settings.debug_mode:
            print(f"【デバッグ】RedisキューにTask ID={task.task_id}, job_type={job_type}を投入しました")
    else:
        if settings.debug_mode:
            print(f"【デバッグ】参考論文のためキューへの投入をスキップしました")

    return UploadResponse(
        message="Upload successful" if not is_reference else "Reference paper registered",
        paper_id=paper.paper_id,
        version_id=version.version_id,
        task_id=task.task_id
    )


@router.get("/tasks/{task_id}", response_model=InferenceTaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """タスク詳細を取得"""
    task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    """論文を論理削除"""
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    paper.is_deleted = True
    db.commit()

    return {"message": "Paper deleted successfully", "paper_id": paper_id}


@router.get("/versions/{version_id}/feedback", response_model=FeedbackResponse)
def get_feedback(version_id: int, db: Session = Depends(get_db)):
    """特定バージョンのフィードバックを取得"""
    feedback = db.query(Feedback).filter(Feedback.version_id == version_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback

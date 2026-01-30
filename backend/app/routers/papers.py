"""
論文ルーター
Phase 1.5: SSE対応・参照モード対応
Phase 1-3: バージョン履歴表示改善
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Set
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


def find_root_paper(db: Session, paper: Paper) -> Paper:
    """
    指定された論文のルート（起点）論文を取得

    親論文を再帰的に遡り、parent_paper_id が None の論文を返す
    """
    current = paper
    visited: Set[int] = set()  # 無限ループ防止

    while current.parent_paper_id is not None:
        if current.paper_id in visited:
            break  # 循環参照があれば終了
        visited.add(current.paper_id)

        parent = db.query(Paper).filter(Paper.paper_id == current.parent_paper_id).first()
        if not parent:
            break
        current = parent

    return current


def find_all_descendant_papers(db: Session, root_paper_id: int) -> List[Paper]:
    """
    ルート論文から派生した全ての子孫論文を取得（ルート含む）

    BFS（幅優先探索）で parent_paper_id を辿る
    """
    all_papers = []
    visited: Set[int] = set()
    queue = [root_paper_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        paper = db.query(Paper).filter(Paper.paper_id == current_id).first()
        if paper:
            all_papers.append(paper)

            # この論文を親とする子論文を探す
            children = db.query(Paper).filter(Paper.parent_paper_id == current_id).all()
            for child in children:
                if child.paper_id not in visited:
                    queue.append(child.paper_id)

    return all_papers


@router.get("/", response_model=List[PaperListItem])
def list_papers(db: Session = Depends(get_db)):
    """
    論文一覧を取得（ルート論文のみ）

    Phase 1-3改善:
    - 親論文を持たない（parent_paper_id = None）ルート論文のみを返す
    - 再提出（リビジョン）された論文はバージョン履歴で確認する
    - 最新の子孫論文のタスク情報を表示
    """
    # ルート論文のみ取得（parent_paper_id が None のもの）
    root_papers = db.query(Paper).filter(
        Paper.is_deleted == False,
        Paper.parent_paper_id == None  # ルート論文のみ
    ).order_by(Paper.created_at.desc()).all()

    result = []
    for root_paper in root_papers:
        # このルート論文の全ての子孫を取得
        all_family_papers = find_all_descendant_papers(db, root_paper.paper_id)

        # 全子孫の中から最新のバージョンとタスクを探す
        latest_version = None
        latest_task = None

        for family_paper in all_family_papers:
            versions = db.query(Version).filter(
                Version.paper_id == family_paper.paper_id
            ).order_by(desc(Version.version_number)).all()

            for ver in versions:
                if latest_version is None or ver.version_number > latest_version.version_number:
                    latest_version = ver
                    # このバージョンの最新タスクを取得
                    task = db.query(InferenceTask).filter(
                        InferenceTask.version_id == ver.version_id
                    ).order_by(desc(InferenceTask.created_at)).first()
                    if task:
                        latest_task = task

        # 最新の子孫論文のステータスを表示に使用
        latest_paper = max(all_family_papers, key=lambda p: p.created_at) if all_family_papers else root_paper

        item = PaperListItem(
            paper_id=root_paper.paper_id,  # ルート論文のIDを表示
            owner_id=root_paper.owner_id,
            conference_id=latest_paper.conference_id,  # 最新の学会ID
            parent_paper_id=None,  # ルートなので必ずNone
            title=root_paper.title,  # ルート論文のタイトル
            status=latest_paper.status,  # 最新論文のステータス
            created_at=root_paper.created_at,
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
    """
    論文のバージョン履歴を取得（親子関係を含む全履歴）

    Phase 1-3改善:
    1. 指定されたpaper_idからルート論文を特定
    2. ルート論文から全ての子孫論文を取得
    3. 全論文のバージョンを統合してソート

    これにより、再提出を繰り返した論文の全変遷を一覧できる
    """
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # ルート論文を特定
    root_paper = find_root_paper(db, paper)

    # ルート論文から全ての子孫論文を取得
    all_family_papers = find_all_descendant_papers(db, root_paper.paper_id)

    # 全論文のバージョンを収集
    all_versions = []
    for family_paper in all_family_papers:
        versions = db.query(Version).filter(
            Version.paper_id == family_paper.paper_id
        ).all()
        all_versions.extend(versions)

    # バージョン番号でソート（降順: 最新が先頭）
    all_versions.sort(key=lambda v: (v.version_number, v.created_at), reverse=True)

    return all_versions


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    title: str = Form(...),
    file: UploadFile = File(...),
    is_reference: Optional[bool] = Form(False),
    conference_id: Optional[str] = Form(None),
    parent_paper_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """
    論文をアップロード

    Args:
        title: 論文タイトル
        file: アップロードファイル（PDF, ZIP, TeX, DOCX）
        is_reference: 参考論文フラグ（True=解析スキップ）
        conference_id: 対象学会のID（ConferenceRuleのrule_id）
        parent_paper_id: 再提出の場合、前回の論文ID

    フロー:
    1. ファイルをローカルボリュームに保存
    2. Paper レコード作成（conference_id, parent_paper_id含む）
    3. Version レコード作成 (version_number自動決定)
    4. File レコード作成
    5. InferenceTask レコード作成 (status=Pending)
    6. Redisにタスクを投入（job_type, conference_id含む）
    """
    if settings.debug_mode:
        print(f"【デバッグ】論文アップロード受信: タイトル='{title}', ファイル='{file.filename}', is_reference={is_reference}, conference_id={conference_id}, parent_paper_id={parent_paper_id}")

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

    # conference_idの検証（指定されている場合）
    if conference_id:
        from ..models import ConferenceRule
        conf = db.query(ConferenceRule).filter(ConferenceRule.rule_id == conference_id).first()
        if not conf:
            raise HTTPException(status_code=400, detail=f"Conference rule '{conference_id}' not found")

    # parent_paper_idの検証（指定されている場合）
    if parent_paper_id:
        parent = db.query(Paper).filter(Paper.paper_id == parent_paper_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail=f"Parent paper '{parent_paper_id}' not found")

    paper = Paper(
        owner_id=1,  # デモユーザー（Phase 2でOAuth実装時に変更）
        title=title,
        status=initial_status,
        conference_id=conference_id,
        parent_paper_id=parent_paper_id
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    if settings.debug_mode:
        print(f"【デバッグ】Paper作成: paper_id={paper.paper_id}, conference_id={conference_id}, parent_paper_id={parent_paper_id}")

    # 2. Version作成
    # 再提出の場合は親論文のバージョン数+1
    version_number = 1
    if parent_paper_id:
        max_version = db.query(Version).join(Paper).filter(
            (Paper.paper_id == parent_paper_id) | (Paper.parent_paper_id == parent_paper_id)
        ).order_by(desc(Version.version_number)).first()
        if max_version:
            version_number = max_version.version_number + 1

    version = Version(
        paper_id=paper.paper_id,
        version_number=version_number
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
        status=initial_task_status,
        conference_rule_id=conference_id  # 学会ルールを紐付け
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if settings.debug_mode:
        print(f"【デバッグ】InferenceTask作成: task_id={task.task_id}, status={initial_task_status}, conference_rule_id={conference_id}")

    # 5. Redisにタスク追加（参考論文でない場合のみ）
    if not is_reference:
        job_type = "ANALYSIS"
        # Phase 1-3: conference_id と parent_paper_id をペイロードに含める
        push_task_with_payload(
            task.task_id,
            job_type,
            conference_id=conference_id,
            parent_paper_id=parent_paper_id
        )

        if settings.debug_mode:
            print(f"【デバッグ】RedisキューにTask ID={task.task_id}, job_type={job_type}, conference_id={conference_id}を投入しました")
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

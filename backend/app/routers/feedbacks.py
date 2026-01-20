from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import Feedback, Version, InferenceTask
from ..schemas import FeedbackResponse, InferenceTaskResponse

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])


@router.get("/version/{version_id}", response_model=List[FeedbackResponse])
def get_feedbacks_by_version(version_id: int, db: Session = Depends(get_db)):
    """Get all feedbacks for a specific version."""
    version = db.query(Version).filter(Version.version_id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version.feedbacks


@router.get("/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    """Get specific feedback by ID."""
    feedback = db.query(Feedback).filter(Feedback.feedback_id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@router.get("/task/{task_id}", response_model=InferenceTaskResponse)
def get_task_status(task_id: int, db: Session = Depends(get_db)):
    """Get inference task status."""
    task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/pending", response_model=List[InferenceTaskResponse])
def get_pending_tasks(db: Session = Depends(get_db)):
    """Get all pending inference tasks."""
    return db.query(InferenceTask).filter(InferenceTask.status == "Pending").all()


@router.get("/tasks/processing", response_model=List[InferenceTaskResponse])
def get_processing_tasks(db: Session = Depends(get_db)):
    """Get all currently processing tasks."""
    return db.query(InferenceTask).filter(InferenceTask.status == "Processing").all()

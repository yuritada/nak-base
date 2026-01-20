from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import User, Paper, Version, Feedback
from ..schemas import DashboardResponse, StudentPaperSummary, ConferenceRuleResponse
from ..models import ConferenceRule
from typing import List

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/professor", response_model=DashboardResponse)
def get_professor_dashboard(db: Session = Depends(get_db)):
    """
    Get professor dashboard with all students' paper summaries.
    Shows latest version and scores for each paper.
    """
    # Get counts
    total_students = db.query(User).filter(User.role == "Student").count()
    total_papers = db.query(Paper).count()
    papers_in_progress = db.query(Paper).filter(Paper.status == "Processing").count()
    papers_completed = db.query(Paper).filter(Paper.status == "Completed").count()

    # Get student papers with latest versions
    student_papers = []

    students = db.query(User).filter(User.role == "Student").all()
    for student in students:
        papers = db.query(Paper).filter(Paper.user_id == student.user_id).all()
        for paper in papers:
            # Get latest version
            latest_version = db.query(Version).filter(
                Version.paper_id == paper.paper_id
            ).order_by(Version.version_number.desc()).first()

            latest_score = None
            if latest_version:
                # Get latest feedback
                feedback = db.query(Feedback).filter(
                    Feedback.version_id == latest_version.version_id
                ).first()
                if feedback:
                    latest_score = feedback.score_json

            student_papers.append(StudentPaperSummary(
                user_id=student.user_id,
                user_name=student.name,
                paper_id=paper.paper_id,
                paper_title=paper.title,
                latest_version=latest_version.version_number if latest_version else 0,
                status=paper.status,
                latest_score=latest_score
            ))

    return DashboardResponse(
        total_students=total_students,
        total_papers=total_papers,
        papers_in_progress=papers_in_progress,
        papers_completed=papers_completed,
        student_papers=student_papers
    )


@router.get("/student/{user_id}")
def get_student_dashboard(user_id: int, db: Session = Depends(get_db)):
    """Get student's own papers and feedback history."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return {"error": "User not found"}

    papers = db.query(Paper).filter(Paper.user_id == user_id).all()

    result = []
    for paper in papers:
        versions = db.query(Version).filter(
            Version.paper_id == paper.paper_id
        ).order_by(Version.version_number.desc()).all()

        version_data = []
        for v in versions:
            feedback = db.query(Feedback).filter(
                Feedback.version_id == v.version_id
            ).first()

            version_data.append({
                "version_id": v.version_id,
                "version_number": v.version_number,
                "file_name": v.file_name,
                "created_at": v.created_at,
                "feedback": {
                    "score_json": feedback.score_json,
                    "comments_json": feedback.comments_json,
                    "overall_summary": feedback.overall_summary
                } if feedback else None
            })

        result.append({
            "paper_id": paper.paper_id,
            "title": paper.title,
            "target_conference": paper.target_conference,
            "status": paper.status,
            "versions": version_data
        })

    return {
        "user_id": user_id,
        "name": user.name,
        "papers": result
    }


@router.get("/conference-rules", response_model=List[ConferenceRuleResponse])
def get_conference_rules(db: Session = Depends(get_db)):
    """Get all available conference rules."""
    return db.query(ConferenceRule).all()

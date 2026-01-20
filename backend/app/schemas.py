from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime


# User schemas
class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Paper schemas
class PaperBase(BaseModel):
    title: str
    target_conference: Optional[str] = None


class PaperCreate(PaperBase):
    pass


class PaperResponse(PaperBase):
    paper_id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaperWithVersions(PaperResponse):
    versions: List["VersionResponse"] = []


# Version schemas
class VersionBase(BaseModel):
    file_name: Optional[str] = None
    file_type: Optional[str] = None


class VersionCreate(VersionBase):
    paper_id: int
    drive_file_id: str


class VersionResponse(VersionBase):
    version_id: int
    paper_id: int
    drive_file_id: str
    version_number: int
    created_at: datetime

    class Config:
        from_attributes = True


# Feedback schemas
class FeedbackBase(BaseModel):
    score_json: Optional[dict] = None
    comments_json: Optional[dict] = None
    overall_summary: Optional[str] = None


class FeedbackResponse(FeedbackBase):
    feedback_id: int
    version_id: int
    report_drive_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Inference Task schemas
class InferenceTaskCreate(BaseModel):
    version_id: int
    conference_rule_id: Optional[str] = "GENERAL"


class InferenceTaskResponse(BaseModel):
    task_id: int
    version_id: int
    status: str
    error_message: Optional[str] = None
    conference_rule_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Upload response
class UploadResponse(BaseModel):
    message: str
    paper_id: int
    version_id: int
    task_id: int


# Conference Rule schemas
class ConferenceRuleResponse(BaseModel):
    rule_id: str
    name: str
    format_rules: Optional[dict] = None
    style_guide: Optional[str] = None

    class Config:
        from_attributes = True


# Dashboard schemas for Professor view
class StudentPaperSummary(BaseModel):
    user_id: int
    user_name: str
    paper_id: int
    paper_title: str
    latest_version: int
    status: str
    latest_score: Optional[dict] = None


class DashboardResponse(BaseModel):
    total_students: int
    total_papers: int
    papers_in_progress: int
    papers_completed: int
    student_papers: List[StudentPaperSummary]

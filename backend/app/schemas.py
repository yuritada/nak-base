"""
Phase 1 Pydanticスキーマ
8テーブル構成対応
"""
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# User schemas
class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Paper schemas
class PaperCreate(BaseModel):
    title: str
    target_conference: Optional[str] = None


class PaperResponse(BaseModel):
    id: int
    user_id: int
    title: str
    target_conference: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Version schemas
class VersionResponse(BaseModel):
    id: int
    paper_id: int
    version_number: int
    created_at: datetime

    class Config:
        from_attributes = True


# File schemas
class FileResponse(BaseModel):
    id: int
    version_id: int
    file_path: str
    file_type: str
    original_filename: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# PaperAuthor schemas
class PaperAuthorCreate(BaseModel):
    author_name: str
    author_order: int = 1
    affiliation: Optional[str] = None
    is_corresponding: bool = False


class PaperAuthorResponse(BaseModel):
    id: int
    paper_id: int
    author_name: str
    author_order: int
    affiliation: Optional[str] = None
    is_corresponding: bool

    class Config:
        from_attributes = True


# InferenceTask schemas
class InferenceTaskResponse(BaseModel):
    id: int
    version_id: int
    status: str
    retry_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Feedback schemas
class FeedbackResponse(BaseModel):
    id: int
    version_id: int
    task_id: Optional[int] = None
    score_json: Optional[dict] = None
    comments_json: Optional[Any] = None
    summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Embedding schemas (for API responses)
class EmbeddingResponse(BaseModel):
    id: int
    file_id: int
    chunk_index: int
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    content_chunk: str
    location_json: Optional[dict] = None

    class Config:
        from_attributes = True


# Combined response schemas
class VersionWithFiles(VersionResponse):
    files: List[FileResponse] = []


class VersionWithDetails(VersionResponse):
    files: List[FileResponse] = []
    feedbacks: List[FeedbackResponse] = []
    inference_tasks: List[InferenceTaskResponse] = []


class PaperWithVersions(PaperResponse):
    versions: List[VersionResponse] = []
    authors: List[PaperAuthorResponse] = []


class PaperWithDetails(PaperResponse):
    versions: List[VersionWithDetails] = []
    authors: List[PaperAuthorResponse] = []


# Upload response
class UploadResponse(BaseModel):
    message: str
    paper_id: int
    version_id: int
    file_id: int
    task_id: int


# Auth schemas
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Legacy compatibility (for frontend during transition)
class LegacyTaskResponse(BaseModel):
    """MVP互換用 - フロントエンド移行期間中のみ使用"""
    id: int
    paper_id: int
    file_path: str
    parsed_text: Optional[str] = None
    status: str
    result_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LegacyPaperWithTasks(PaperResponse):
    """MVP互換用"""
    tasks: List[LegacyTaskResponse] = []

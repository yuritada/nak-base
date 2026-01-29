"""
nak-base Pydanticスキーマ
Phase 1-1: 新モデル構造対応
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ================== Enum Definitions ==================

class UserRoleEnum(str, Enum):
    ADMIN = "Admin"
    PROFESSOR = "Professor"
    STUDENT = "Student"


class FileRoleEnum(str, Enum):
    MAIN_PDF = "main_pdf"
    SOURCE_TEX = "source_tex"
    ADDITIONAL_FILE = "additional_file"


class TaskStatusEnum(str, Enum):
    PENDING = "Pending"
    PARSING = "Parsing"
    RAG = "RAG"
    LLM = "LLM"
    COMPLETED = "Completed"
    ERROR = "Error"


class PaperStatusEnum(str, Enum):
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    ERROR = "Error"


# ================== User Schemas ==================

class UserBase(BaseModel):
    email: str
    name: str


class UserCreate(UserBase):
    role: UserRoleEnum = UserRoleEnum.STUDENT


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: UserRoleEnum
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== Paper Schemas ==================

class PaperCreate(BaseModel):
    title: str


class PaperResponse(BaseModel):
    paper_id: int
    owner_id: Optional[int] = None
    title: str
    status: PaperStatusEnum
    is_deleted: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== Version Schemas ==================

class VersionResponse(BaseModel):
    version_id: int
    paper_id: int
    version_number: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== File Schemas ==================

class FileResponse(BaseModel):
    file_id: int
    version_id: int
    file_role: FileRoleEnum
    is_primary: bool
    cache_path: Optional[str] = None
    is_cached: bool
    original_filename: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== InferenceTask Schemas ==================

class InferenceTaskResponse(BaseModel):
    task_id: int
    version_id: int
    status: TaskStatusEnum
    error_message: Optional[str] = None
    retry_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== Feedback Schemas ==================

class FeedbackResponse(BaseModel):
    feedback_id: int
    version_id: int
    task_id: Optional[int] = None
    score_json: Optional[dict] = None
    comments_json: Optional[dict] = None
    overall_summary: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ================== Composite Schemas ==================

class VersionWithFiles(VersionResponse):
    files: List[FileResponse] = []


class PaperWithVersions(PaperResponse):
    versions: List[VersionResponse] = []


class PaperDetail(PaperResponse):
    versions: List[VersionWithFiles] = []


# ================== Upload Response ==================

class UploadResponse(BaseModel):
    message: str
    paper_id: int
    version_id: int
    task_id: int


# ================== Auth Schemas ==================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ================== Legacy Compatibility (MVP) ==================
# These schemas maintain backward compatibility during transition

class LegacyTaskResponse(BaseModel):
    """MVP互換: 旧Taskスキーマ（InferenceTaskへのマッピング用）"""
    id: int
    paper_id: int
    file_path: Optional[str] = None
    parsed_text: Optional[str] = None
    status: str
    result_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LegacyPaperResponse(BaseModel):
    """MVP互換: 旧Paperスキーマ"""
    id: int
    user_id: int
    title: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LegacyPaperWithTasks(LegacyPaperResponse):
    """MVP互換: 旧PaperWithTasksスキーマ"""
    tasks: List[LegacyTaskResponse] = []

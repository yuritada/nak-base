"""
MVP版 Pydanticスキーマ
"""
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


# User schemas
class UserResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# Paper schemas
class PaperCreate(BaseModel):
    title: str


class PaperResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaperWithTasks(PaperResponse):
    tasks: List["TaskResponse"] = []


# Task schemas
class TaskResponse(BaseModel):
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


# Upload response
class UploadResponse(BaseModel):
    message: str
    paper_id: int
    task_id: int


# Auth schemas
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

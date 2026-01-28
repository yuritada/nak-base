"""
Phase 1 Worker用データモデル
8テーブル構成: users, papers, versions, files, paper_authors,
feedbacks, embeddings, inference_tasks
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .database import Base


class User(Base):
    """ユーザーテーブル"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="student")
    google_id = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    papers = relationship("Paper", back_populates="user")


class Paper(Base):
    """論文メタデータ"""
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    target_conference = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="papers")
    versions = relationship("Version", back_populates="paper")


class Version(Base):
    """版管理用"""
    __tablename__ = "versions"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())

    paper = relationship("Paper", back_populates="versions")
    files = relationship("File", back_populates="version")
    feedbacks = relationship("Feedback", back_populates="version")
    inference_tasks = relationship("InferenceTask", back_populates="version")


class File(Base):
    """ファイルパス管理"""
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False, default="pdf")
    original_filename = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=True)
    drive_file_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    version = relationship("Version", back_populates="files")
    embeddings = relationship("Embedding", back_populates="file")


class PaperAuthor(Base):
    """著者情報の正規化"""
    __tablename__ = "paper_authors"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    author_name = Column(String(255), nullable=False)
    author_order = Column(Integer, nullable=False, default=1)
    affiliation = Column(String(255), nullable=True)
    is_corresponding = Column(Boolean, nullable=False, default=False)


class Feedback(Base):
    """AIによる評価データ"""
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("inference_tasks.id", ondelete="SET NULL"), nullable=True)
    report_drive_id = Column(String(255), nullable=True)
    score_json = Column(JSONB, nullable=True)
    comments_json = Column(JSONB, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    version = relationship("Version", back_populates="feedbacks")
    task = relationship("InferenceTask", back_populates="feedback")


class Embedding(Base):
    """RAG用ベクトルデータ"""
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(255), nullable=True)
    page_number = Column(Integer, nullable=True)
    line_number = Column(Integer, nullable=True)
    content_chunk = Column(Text, nullable=False)
    location_json = Column(JSONB, nullable=True)
    embedding = Column(Vector(768), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    file = relationship("File", back_populates="embeddings")


class InferenceTask(Base):
    """非同期処理の状態管理"""
    __tablename__ = "inference_tasks"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    version = relationship("Version", back_populates="inference_tasks")
    feedback = relationship("Feedback", back_populates="task", uselist=False)

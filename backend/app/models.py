"""
nak-base 完成形データモデル
設計資料集に基づく全10テーブル構成

Enum値は全て大文字で統一（DB側と一致させる）
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Enum as SQLEnum, CheckConstraint, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import enum

from .database import Base


# ================== Enum Definitions (全大文字で統一) ==================

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    PROFESSOR = "PROFESSOR"
    STUDENT = "STUDENT"


class FileRole(str, enum.Enum):
    MAIN_PDF = "MAIN_PDF"
    MAIN_DOCX = "MAIN_DOCX"
    SOURCE_TEX = "SOURCE_TEX"
    ADDITIONAL_FILE = "ADDITIONAL_FILE"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    RAG = "RAG"
    LLM = "LLM"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class PaperStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PARSED = "PARSED"
    EMBEDDED = "EMBEDDED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


# ================== Table Definitions ==================

class User(Base):
    """
    1. users (ユーザー管理)
    大学のGoogle認証（OAuth2）を起点とするユーザーテーブル
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.STUDENT)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    owned_papers = relationship("Paper", back_populates="owner")
    paper_authorships = relationship("PaperAuthor", back_populates="user")


class Paper(Base):
    """
    2. papers (論文基本情報)
    論文の箱となるメタデータ
    主キーは paper_id で統一

    Phase 1-3: conference_id, parent_paper_id 追加
    - conference_id: どの学会向けの論文か
    - parent_paper_id: 再提出の場合、前回の論文ID（バージョニング）
    """
    __tablename__ = "papers"

    paper_id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conference_id = Column(String(50), ForeignKey("conference_rules.rule_id", ondelete="SET NULL"), nullable=True)
    parent_paper_id = Column(Integer, ForeignKey("papers.paper_id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False)
    status = Column(SQLEnum(PaperStatus), nullable=False, default=PaperStatus.PROCESSING)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", back_populates="owned_papers")
    conference = relationship("ConferenceRule", back_populates="papers")
    parent_paper = relationship("Paper", remote_side="Paper.paper_id", backref="child_papers")
    authors = relationship("PaperAuthor", back_populates="paper", cascade="all, delete-orphan")
    versions = relationship("Version", back_populates="paper", cascade="all, delete-orphan")


class PaperAuthor(Base):
    """
    3. paper_authors (著者管理 - 中間テーブル)
    1つの論文に連なる複数の著者を管理
    """
    __tablename__ = "paper_authors"

    paper_id = Column(Integer, ForeignKey("papers.paper_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    author_order = Column(Integer, nullable=False, default=1)
    is_corresponding_author = Column(Boolean, nullable=False, default=False)

    # Relationships
    paper = relationship("Paper", back_populates="authors")
    user = relationship("User", back_populates="paper_authorships")

    __table_args__ = (
        PrimaryKeyConstraint("paper_id", "user_id"),
    )


class Version(Base):
    """
    4. versions (論文バージョン管理)
    「第n回提出」という時間軸の管理
    """
    __tablename__ = "versions"

    version_id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.paper_id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    paper = relationship("Paper", back_populates="versions")
    files = relationship("File", back_populates="version", cascade="all, delete-orphan")
    feedbacks = relationship("Feedback", back_populates="version", cascade="all, delete-orphan")
    inference_tasks = relationship("InferenceTask", back_populates="version", cascade="all, delete-orphan")

    # version_diffs relationships
    current_diffs = relationship(
        "VersionDiff",
        foreign_keys="VersionDiff.current_version_id",
        back_populates="current_version",
        cascade="all, delete-orphan"
    )
    previous_diffs = relationship(
        "VersionDiff",
        foreign_keys="VersionDiff.previous_version_id",
        back_populates="previous_version"
    )


class File(Base):
    """
    5. files (ファイル実体管理)
    1つのバージョンに含まれるPDF、TeX、画像などの実体管理
    """
    __tablename__ = "files"

    file_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    file_role = Column(SQLEnum(FileRole), nullable=False, default=FileRole.MAIN_PDF)
    is_primary = Column(Boolean, nullable=False, default=False)
    drive_file_id = Column(String(255), nullable=True)
    cache_path = Column(String(500), nullable=True)
    is_cached = Column(Boolean, nullable=False, default=True)
    file_hash = Column(String(128), nullable=True)
    original_filename = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    version = relationship("Version", back_populates="files")
    embeddings = relationship("Embedding", back_populates="file", cascade="all, delete-orphan")


class Feedback(Base):
    """
    6. feedbacks (解析結果報告)
    AI Workerが出力した最終成果
    """
    __tablename__ = "feedbacks"

    feedback_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("inference_tasks.task_id", ondelete="SET NULL"), nullable=True)
    score_json = Column(JSONB, nullable=True)
    comments_json = Column(JSONB, nullable=True)
    overall_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    version = relationship("Version", back_populates="feedbacks")
    task = relationship("InferenceTask", back_populates="feedback")


class InferenceTask(Base):
    """
    7. inference_tasks (タスク監視・リトライ管理)
    非同期処理の実行状態。フロントエンドの進捗表示のソース
    """
    __tablename__ = "inference_tasks"

    task_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    conference_rule_id = Column(String(50), ForeignKey("conference_rules.rule_id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    version = relationship("Version", back_populates="inference_tasks")
    conference_rule = relationship("ConferenceRule", back_populates="inference_tasks")
    feedback = relationship("Feedback", back_populates="task", uselist=False)


class Embedding(Base):
    """
    8. embeddings (RAG・ベクトル検索用)
    pgvector を使用した検索用データ

    Phase 1-3: nomic-embed-text (768次元) を使用
    """
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(255), nullable=True)
    page_number = Column(Integer, nullable=True)
    line_number = Column(Integer, nullable=True)
    content_chunk = Column(Text, nullable=False)
    location_json = Column(JSONB, nullable=True)  # {"page": 1, "bbox": [x0, y0, x1, y1]}
    embedding = Column(Vector(768), nullable=True)  # nomic-embed-text dimension
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    file = relationship("File", back_populates="embeddings")


class ConferenceRule(Base):
    """
    9. conference_rules (学会別ルール定義)

    Phase 1-3: プロンプトに埋め込む学会ルール
    - format_rules: JSON形式のフォーマット規定（ページ数、フォントサイズ等）
    - style_guide: テキスト形式のスタイルガイド（プロンプトに直接埋め込み）
    - embedding: スタイルガイドのベクトル表現（セマンティック検索用）
    """
    __tablename__ = "conference_rules"

    rule_id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    format_rules = Column(JSONB, nullable=True)
    style_guide = Column(Text, nullable=True)
    embedding = Column(Vector(768), nullable=True)  # セマンティック検索用ベクトル
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    inference_tasks = relationship("InferenceTask", back_populates="conference_rule")
    papers = relationship("Paper", back_populates="conference")


class VersionDiff(Base):
    """
    10. version_diffs (バージョン間差分管理)
    """
    __tablename__ = "version_diffs"

    diff_id = Column(Integer, primary_key=True, index=True)
    current_version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    previous_version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="SET NULL"), nullable=True)
    text_diff_json = Column(JSONB, nullable=True)
    semantic_diff_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    current_version = relationship(
        "Version",
        foreign_keys=[current_version_id],
        back_populates="current_diffs"
    )
    previous_version = relationship(
        "Version",
        foreign_keys=[previous_version_id],
        back_populates="previous_diffs"
    )

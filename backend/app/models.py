from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    papers = relationship("Paper", back_populates="user")

    __table_args__ = (
        CheckConstraint(role.in_(['Student', 'Professor']), name='check_user_role'),
    )


class Paper(Base):
    __tablename__ = "papers"

    paper_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    target_conference = Column(String(255))
    status = Column(String(20), nullable=False, default="Draft")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="papers")
    versions = relationship("Version", back_populates="paper")

    __table_args__ = (
        CheckConstraint(status.in_(['Draft', 'Processing', 'Completed', 'Error']), name='check_paper_status'),
    )


class Version(Base):
    __tablename__ = "versions"

    version_id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.paper_id", ondelete="CASCADE"), nullable=False)
    drive_file_id = Column(String(255), nullable=False)
    version_number = Column(Integer, nullable=False)
    file_name = Column(String(500))
    file_type = Column(String(10))
    created_at = Column(DateTime, server_default=func.now())

    paper = relationship("Paper", back_populates="versions")
    feedbacks = relationship("Feedback", back_populates="version")
    inference_tasks = relationship("InferenceTask", back_populates="version")


class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    report_drive_id = Column(String(255))
    score_json = Column(JSONB)
    comments_json = Column(JSONB)
    overall_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    version = relationship("Version", back_populates="feedbacks")


class Seminar(Base):
    __tablename__ = "seminars"

    doc_id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    content_vector = Column(Vector(768))
    meta_data = Column(JSONB)
    doc_type = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())


class InferenceTask(Base):
    __tablename__ = "inference_tasks"

    task_id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("versions.version_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="Pending")
    error_message = Column(Text)
    conference_rule_id = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    version = relationship("Version", back_populates="inference_tasks")


class ConferenceRule(Base):
    __tablename__ = "conference_rules"

    rule_id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    format_rules = Column(JSONB)
    style_guide = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

"""Phase 1 Schema - Complete rewrite for RAG foundation

Revision ID: 001_phase1
Revises:
Create Date: 2026-01-28

Breaking change: Drops MVP tables and creates 8-table schema with pgvector support.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_phase1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Drop old MVP tables if they exist (breaking change)
    op.execute("DROP TABLE IF EXISTS tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS papers CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='student'),
        sa.Column('google_id', sa.String(255), unique=True, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('student', 'professor', 'admin')", name='check_user_role')
    )
    op.create_index('idx_users_email', 'users', ['email'])

    # Create papers table
    op.create_table(
        'papers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('target_conference', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft', 'processing', 'completed', 'error')", name='check_paper_status')
    )
    op.create_index('idx_papers_user_id', 'papers', ['user_id'])
    op.create_index('idx_papers_status', 'papers', ['status'])

    # Create versions table
    op.create_table(
        'versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_versions_paper_id', 'versions', ['paper_id'])

    # Create files table
    op.create_table(
        'files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('versions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False, server_default='pdf'),
        sa.Column('original_filename', sa.String(500), nullable=True),
        sa.Column('file_hash', sa.String(64), nullable=True),
        sa.Column('drive_file_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_files_version_id', 'files', ['version_id'])
    op.create_index('idx_files_hash', 'files', ['file_hash'])

    # Create paper_authors table
    op.create_table(
        'paper_authors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_name', sa.String(255), nullable=False),
        sa.Column('author_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('affiliation', sa.String(255), nullable=True),
        sa.Column('is_corresponding', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('idx_paper_authors_paper_id', 'paper_authors', ['paper_id'])

    # Create inference_tasks table (before feedbacks due to FK)
    op.create_table(
        'inference_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('versions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'parsing', 'rag', 'llm', 'completed', 'error')",
            name='check_inference_task_status'
        ),
        sa.CheckConstraint('retry_count <= 3', name='check_retry_count_max'),
    )
    op.create_index('idx_inference_tasks_version_id', 'inference_tasks', ['version_id'])
    op.create_index('idx_inference_tasks_status', 'inference_tasks', ['status'])

    # Create feedbacks table
    op.create_table(
        'feedbacks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('versions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('inference_tasks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('report_drive_id', sa.String(255), nullable=True),
        sa.Column('score_json', postgresql.JSONB(), nullable=True),
        sa.Column('comments_json', postgresql.JSONB(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_feedbacks_version_id', 'feedbacks', ['version_id'])
    op.create_index('idx_feedbacks_task_id', 'feedbacks', ['task_id'])

    # Create embeddings table with pgvector
    # Note: Using raw SQL for vector type as Alembic doesn't natively support it
    op.execute("""
        CREATE TABLE embeddings (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            section_title VARCHAR(255),
            page_number INTEGER,
            line_number INTEGER,
            content_chunk TEXT NOT NULL,
            location_json JSONB,
            embedding vector(768),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.create_index('idx_embeddings_file_id', 'embeddings', ['file_id'])

    # Create vector similarity index (IVFFlat for approximate nearest neighbor)
    op.execute("""
        CREATE INDEX idx_embeddings_vector ON embeddings
        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)

    # Insert demo user for Phase 1 compatibility
    op.execute("""
        INSERT INTO users (id, email, name, role)
        VALUES (1, 'demo@example.com', 'Demo User', 'student')
    """)

    # Reset sequence to avoid conflicts
    op.execute("SELECT setval('users_id_seq', 1, true)")


def downgrade() -> None:
    # Drop all Phase 1 tables in reverse dependency order
    op.drop_table('embeddings')
    op.drop_table('feedbacks')
    op.drop_table('inference_tasks')
    op.drop_table('paper_authors')
    op.drop_table('files')
    op.drop_table('versions')
    op.drop_table('papers')
    op.drop_table('users')
    op.execute("DROP EXTENSION IF EXISTS vector")

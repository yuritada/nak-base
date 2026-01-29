"""Initial schema - Phase 1-1 DB Refresh

Revision ID: 001_initial
Revises:
Create Date: 2025-01-29

Creates all 10 tables as defined in the design document:
1. users
2. papers
3. paper_authors
4. versions
5. files
6. feedbacks
7. inference_tasks
8. embeddings (with pgvector)
9. conference_rules
10. version_diffs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create Enum types
    userrole_enum = postgresql.ENUM('Admin', 'Professor', 'Student', name='userrole', create_type=False)
    filerole_enum = postgresql.ENUM('main_pdf', 'source_tex', 'additional_file', name='filerole', create_type=False)
    taskstatus_enum = postgresql.ENUM('Pending', 'Parsing', 'RAG', 'LLM', 'Completed', 'Error', name='taskstatus', create_type=False)
    paperstatus_enum = postgresql.ENUM('Processing', 'Completed', 'Error', name='paperstatus', create_type=False)

    userrole_enum.create(op.get_bind(), checkfirst=True)
    filerole_enum.create(op.get_bind(), checkfirst=True)
    taskstatus_enum.create(op.get_bind(), checkfirst=True)
    paperstatus_enum.create(op.get_bind(), checkfirst=True)

    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', userrole_enum, nullable=False, server_default='Student'),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 9. conference_rules table (create before inference_tasks due to FK)
    op.create_table(
        'conference_rules',
        sa.Column('rule_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('format_rules', postgresql.JSONB(), nullable=True),
        sa.Column('style_guide', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('rule_id')
    )

    # 2. papers table
    op.create_table(
        'papers',
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('status', paperstatus_enum, nullable=False, server_default='Processing'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('paper_id')
    )
    op.create_index(op.f('ix_papers_paper_id'), 'papers', ['paper_id'], unique=False)

    # 3. paper_authors table
    op.create_table(
        'paper_authors',
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('author_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_corresponding_author', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('paper_id', 'user_id')
    )

    # 4. versions table
    op.create_table(
        'versions',
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.paper_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('version_id')
    )
    op.create_index(op.f('ix_versions_version_id'), 'versions', ['version_id'], unique=False)

    # 5. files table
    op.create_table(
        'files',
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('file_role', filerole_enum, nullable=False, server_default='main_pdf'),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('drive_file_id', sa.String(length=255), nullable=True),
        sa.Column('cache_path', sa.String(length=500), nullable=True),
        sa.Column('is_cached', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('file_hash', sa.String(length=128), nullable=True),
        sa.Column('original_filename', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['version_id'], ['versions.version_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('file_id')
    )
    op.create_index(op.f('ix_files_file_id'), 'files', ['file_id'], unique=False)

    # 7. inference_tasks table
    op.create_table(
        'inference_tasks',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('status', taskstatus_enum, nullable=False, server_default='Pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conference_rule_id', sa.String(length=50), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['version_id'], ['versions.version_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conference_rule_id'], ['conference_rules.rule_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('task_id')
    )
    op.create_index(op.f('ix_inference_tasks_task_id'), 'inference_tasks', ['task_id'], unique=False)

    # 6. feedbacks table
    op.create_table(
        'feedbacks',
        sa.Column('feedback_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('score_json', postgresql.JSONB(), nullable=True),
        sa.Column('comments_json', postgresql.JSONB(), nullable=True),
        sa.Column('overall_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['version_id'], ['versions.version_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['inference_tasks.task_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('feedback_id')
    )
    op.create_index(op.f('ix_feedbacks_feedback_id'), 'feedbacks', ['feedback_id'], unique=False)

    # 8. embeddings table (with pgvector)
    op.create_table(
        'embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('section_title', sa.String(length=255), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('content_chunk', sa.Text(), nullable=False),
        sa.Column('location_json', postgresql.JSONB(), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['file_id'], ['files.file_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_embeddings_id'), 'embeddings', ['id'], unique=False)

    # Create vector index for similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # 10. version_diffs table
    op.create_table(
        'version_diffs',
        sa.Column('diff_id', sa.Integer(), nullable=False),
        sa.Column('current_version_id', sa.Integer(), nullable=False),
        sa.Column('previous_version_id', sa.Integer(), nullable=True),
        sa.Column('text_diff_json', postgresql.JSONB(), nullable=True),
        sa.Column('semantic_diff_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['current_version_id'], ['versions.version_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['previous_version_id'], ['versions.version_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('diff_id')
    )
    op.create_index(op.f('ix_version_diffs_diff_id'), 'version_diffs', ['diff_id'], unique=False)

    # Insert demo user for backward compatibility
    op.execute(
        "INSERT INTO users (id, email, name, role) VALUES (1, 'demo@example.com', 'Demo User', 'Student') ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_version_diffs_diff_id'), table_name='version_diffs')
    op.drop_table('version_diffs')

    op.execute("DROP INDEX IF EXISTS ix_embeddings_vector")
    op.drop_index(op.f('ix_embeddings_id'), table_name='embeddings')
    op.drop_table('embeddings')

    op.drop_index(op.f('ix_feedbacks_feedback_id'), table_name='feedbacks')
    op.drop_table('feedbacks')

    op.drop_index(op.f('ix_inference_tasks_task_id'), table_name='inference_tasks')
    op.drop_table('inference_tasks')

    op.drop_index(op.f('ix_files_file_id'), table_name='files')
    op.drop_table('files')

    op.drop_index(op.f('ix_versions_version_id'), table_name='versions')
    op.drop_table('versions')

    op.drop_table('paper_authors')

    op.drop_index(op.f('ix_papers_paper_id'), table_name='papers')
    op.drop_table('papers')

    op.drop_table('conference_rules')

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS paperstatus")
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS filerole")
    op.execute("DROP TYPE IF EXISTS userrole")

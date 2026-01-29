"""Phase 1-3: RAG Pipeline Support

Revision ID: 002_phase1_3
Revises: 001_initial
Create Date: 2026-01-30

Adds:
1. conference_id and parent_paper_id columns to papers table
2. MAIN_DOCX value to filerole enum
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_phase1_3'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add MAIN_DOCX to filerole enum
    op.execute("ALTER TYPE filerole ADD VALUE IF NOT EXISTS 'MAIN_DOCX'")

    # 2. Add conference_id column to papers table
    op.add_column(
        'papers',
        sa.Column(
            'conference_id',
            sa.String(length=50),
            nullable=True
        )
    )

    # 3. Add parent_paper_id column to papers table (self-referencing FK)
    op.add_column(
        'papers',
        sa.Column(
            'parent_paper_id',
            sa.Integer(),
            nullable=True
        )
    )

    # 4. Add foreign key constraints
    op.create_foreign_key(
        'fk_papers_conference_id',
        'papers',
        'conference_rules',
        ['conference_id'],
        ['rule_id'],
        ondelete='SET NULL'
    )

    op.create_foreign_key(
        'fk_papers_parent_paper_id',
        'papers',
        'papers',
        ['parent_paper_id'],
        ['paper_id'],
        ondelete='SET NULL'
    )

    # 5. Create index for parent_paper_id for efficient queries
    op.create_index(
        'ix_papers_parent_paper_id',
        'papers',
        ['parent_paper_id'],
        unique=False
    )

    # 6. Create index for conference_id for efficient queries
    op.create_index(
        'ix_papers_conference_id',
        'papers',
        ['conference_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_papers_conference_id', table_name='papers')
    op.drop_index('ix_papers_parent_paper_id', table_name='papers')

    # Drop foreign key constraints
    op.drop_constraint('fk_papers_parent_paper_id', 'papers', type_='foreignkey')
    op.drop_constraint('fk_papers_conference_id', 'papers', type_='foreignkey')

    # Drop columns
    op.drop_column('papers', 'parent_paper_id')
    op.drop_column('papers', 'conference_id')

    # Note: Cannot easily remove enum value in PostgreSQL
    # MAIN_DOCX will remain in filerole enum

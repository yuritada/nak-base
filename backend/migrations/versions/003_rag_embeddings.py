"""Phase 1-3: RAG Embeddings Support

Revision ID: 003_rag_embeddings
Revises: 002_phase1_3
Create Date: 2026-01-30

Adds:
1. embedding column to conference_rules table for semantic search
2. Changes embeddings.embedding dimension from 1536 to 768 (nomic-embed-text)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '003_rag_embeddings'
down_revision: Union[str, None] = '002_phase1_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add embedding column to conference_rules
    op.add_column(
        'conference_rules',
        sa.Column('embedding', Vector(768), nullable=True)
    )

    # 2. Alter embeddings.embedding column dimension from 1536 to 768
    # Note: This will clear existing embeddings - acceptable for development
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(768)")

    # 3. Recreate the vector index with correct dimensions
    op.execute("DROP INDEX IF EXISTS ix_embeddings_vector")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # 4. Create index for conference_rules embedding
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conference_rules_embedding ON conference_rules USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )


def downgrade() -> None:
    # Drop conference_rules embedding index
    op.execute("DROP INDEX IF EXISTS ix_conference_rules_embedding")

    # Drop embedding column from conference_rules
    op.drop_column('conference_rules', 'embedding')

    # Revert embeddings.embedding dimension back to 1536
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(1536)")

    # Recreate vector index
    op.execute("DROP INDEX IF EXISTS ix_embeddings_vector")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

-- nak-base Phase 1 Database Initialization
-- pgvector拡張のみ有効化（スキーマはAlembicで管理）

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Note: Full schema is managed by Alembic migrations
-- Run: alembic upgrade head (inside backend container)

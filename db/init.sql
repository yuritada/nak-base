-- nak-base MVP Database Schema
-- シンプルな3テーブル構成
-- <このファイルは非マウントです。実際に読まれていません！！！>

-- Users table (デモユーザーのみ)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL DEFAULT 'Demo User'
);

-- デモユーザーを挿入
INSERT INTO users (id, name) VALUES (1, 'Demo User');

-- Papers table
CREATE TABLE papers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table (versions + inference_tasks + feedbacksを統合)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    parsed_text TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'error')),
    result_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger
CREATE TRIGGER update_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Indexes for better query performance
CREATE INDEX idx_papers_user_id ON papers(user_id);
CREATE INDEX idx_tasks_paper_id ON tasks(paper_id);
CREATE INDEX idx_tasks_status ON tasks(status);

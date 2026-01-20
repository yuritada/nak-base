-- nak-base Database Schema
-- PostgreSQL with pgvector extension

-- Enable pgvector extension for RAG functionality
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('Student', 'Professor')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Papers table
CREATE TABLE papers (
    paper_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    target_conference VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Processing', 'Completed', 'Error')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Versions table
CREATE TABLE versions (
    version_id SERIAL PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    drive_file_id VARCHAR(255) NOT NULL,
    version_number INTEGER NOT NULL,
    file_name VARCHAR(500),
    file_type VARCHAR(10) CHECK (file_type IN ('pdf', 'tex')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(paper_id, version_number)
);

-- Auto-increment version_number per paper
CREATE OR REPLACE FUNCTION set_version_number()
RETURNS TRIGGER AS $$
BEGIN
    SELECT COALESCE(MAX(version_number), 0) + 1
    INTO NEW.version_number
    FROM versions
    WHERE paper_id = NEW.paper_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_set_version_number
BEFORE INSERT ON versions
FOR EACH ROW
EXECUTE FUNCTION set_version_number();

-- Feedbacks table
CREATE TABLE feedbacks (
    feedback_id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    report_drive_id VARCHAR(255),
    score_json JSONB,
    comments_json JSONB,
    overall_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seminars table (RAG Source for past papers and meeting notes)
CREATE TABLE seminars (
    doc_id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    content_vector vector(768),
    meta_data JSONB,
    doc_type VARCHAR(50) CHECK (doc_type IN ('paper', 'meeting_note', 'reference')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for vector similarity search
CREATE INDEX ON seminars USING ivfflat (content_vector vector_cosine_ops) WITH (lists = 100);

-- Inference tasks table (for tracking async jobs)
CREATE TABLE inference_tasks (
    task_id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES versions(version_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Processing', 'Completed', 'Error')),
    error_message TEXT,
    conference_rule_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Conference rules table (DEIM, IPSJ, etc.)
CREATE TABLE conference_rules (
    rule_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    format_rules JSONB,
    style_guide TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default conference rules
INSERT INTO conference_rules (rule_id, name, format_rules, style_guide) VALUES
('DEIM', 'DEIM (Data Engineering and Information Management)',
 '{"page_limit": 8, "columns": 2, "font_size": 10, "margin_top": 25, "margin_bottom": 25}',
 'DEIM論文フォーマットに準拠すること。2段組み、10ptフォント使用。'),
('IPSJ', 'IPSJ (Information Processing Society of Japan)',
 '{"page_limit": 10, "columns": 2, "font_size": 9, "margin_top": 20, "margin_bottom": 20}',
 'IPSJ論文誌フォーマットに準拠すること。'),
('GENERAL', 'General Academic Paper',
 '{"page_limit": null, "columns": 1, "font_size": 12}',
 '一般的な学術論文形式。');

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to relevant tables
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_papers_updated_at
    BEFORE UPDATE ON papers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create indexes for better query performance
CREATE INDEX idx_papers_user_id ON papers(user_id);
CREATE INDEX idx_papers_status ON papers(status);
CREATE INDEX idx_versions_paper_id ON versions(paper_id);
CREATE INDEX idx_feedbacks_version_id ON feedbacks(version_id);
CREATE INDEX idx_inference_tasks_status ON inference_tasks(status);
CREATE INDEX idx_inference_tasks_version_id ON inference_tasks(version_id);

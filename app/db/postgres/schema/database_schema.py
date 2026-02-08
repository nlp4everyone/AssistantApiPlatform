# SQL DDL statement as a Python string
CREATE_ASSISTANTS_TABLE = """
CREATE TABLE IF NOT EXISTS assistants (
    id SERIAL PRIMARY KEY,
    assistant_id TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    description VARCHAR(256) NULL,
    instructions TEXT NULL,
    metadata JSONB NULL,
    name VARCHAR(256) NULL,
    reasoning_effort VARCHAR(16) NULL 
        CHECK (reasoning_effort IN ('minimal', 'low', 'medium', 'high')),
    response_format TEXT NULL,
    temperature DOUBLE PRECISION NULL 
        CHECK (temperature >= 0 AND temperature <= 2),
    tool_resources JSONB NULL,
    tools JSONB NULL,
    top_p DOUBLE PRECISION NULL 
        CHECK (top_p >= 0 AND top_p <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

# Create thread table
CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    metadata JSONB DEFAULT '{}'::jsonb,
    tool_resources JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""

# Create messages table
CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    run_id TEXT,
    content JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    attachments JSONB DEFAULT '[]'::jsonb,
    assistant_id TEXT
);
"""

# Create run table
CREATE_RUN_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    assistant_id TEXT REFERENCES assistants(assistant_id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_error TEXT,
    incomplete_details JSONB,
    max_prompt_tokens INTEGER,
    max_completion_tokens INTEGER,
    usage JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""
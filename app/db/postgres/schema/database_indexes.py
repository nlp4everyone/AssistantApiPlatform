# Indexes for messages table
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_messages_thread_id_created_at
    ON messages(thread_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_thread_id_seq
    ON messages(thread_id, seq);

CREATE INDEX IF NOT EXISTS idx_messages_thread_id
    ON messages(thread_id);
"""

# Indexes for runs table
CREATE_RUN_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_thread_id_seq ON runs(thread_id, seq);
CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id);
CREATE INDEX IF NOT EXISTS idx_runs_assistant_id ON runs(assistant_id);
"""

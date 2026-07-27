CREATE TABLE IF NOT EXISTS potential_simulation_events (
    id VARCHAR(36) PRIMARY KEY,
    resume_id VARCHAR(36) NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    strategy_ids JSONB,
    result_snapshot JSONB NOT NULL,
    rule_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_potential_simulation_resume_created
    ON potential_simulation_events (resume_id, created_at DESC);

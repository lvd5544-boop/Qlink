CREATE TABLE IF NOT EXISTS interview_results (
    id VARCHAR(36) PRIMARY KEY,
    fair_use_session_id VARCHAR(36)
        REFERENCES interview_usage_sessions(id) ON DELETE SET NULL,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id VARCHAR(36) REFERENCES resumes(id) ON DELETE SET NULL,
    application_id VARCHAR(36)
        REFERENCES job_applications(id) ON DELETE SET NULL,
    mode VARCHAR(24) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending_confirmation',
    transcript JSON NOT NULL DEFAULT '[]',
    extracted_json JSON NOT NULL DEFAULT '{}',
    source_references JSON NOT NULL DEFAULT '[]',
    requested_uses JSON NOT NULL DEFAULT '{}',
    allowed_uses JSON NOT NULL DEFAULT '{}',
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_interview_result_fair_use_session
        UNIQUE (fair_use_session_id),
    CONSTRAINT ck_interview_result_mode
        CHECK (mode IN ('profile', 'claim_followup')),
    CONSTRAINT ck_interview_result_status
        CHECK (status IN ('pending_confirmation', 'confirmed', 'revoked'))
);

CREATE INDEX IF NOT EXISTS ix_interview_result_user_status
    ON interview_results (user_id, status, created_at);

CREATE TABLE IF NOT EXISTS legal_acceptances (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    terms_version VARCHAR(32) NOT NULL,
    privacy_notice_version VARCHAR(32) NOT NULL,
    notice_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_legal_acceptance_user_created
    ON legal_acceptances (user_id, accepted_at);

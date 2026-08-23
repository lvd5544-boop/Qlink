CREATE TABLE IF NOT EXISTS pilot_participants (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    participant_code VARCHAR(36) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    withdrawn_at TIMESTAMPTZ,
    CONSTRAINT ck_pilot_participant_status CHECK (status IN ('active', 'withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_pilot_participant_status
    ON pilot_participants (status, created_at);

CREATE TABLE IF NOT EXISTS pilot_consents (
    id VARCHAR(36) PRIMARY KEY,
    participant_id VARCHAR(36) NOT NULL REFERENCES pilot_participants(id) ON DELETE CASCADE,
    consent_version VARCHAR(32) NOT NULL,
    action VARCHAR(20) NOT NULL,
    product_research BOOLEAN NOT NULL DEFAULT TRUE,
    aggregate_metrics BOOLEAN NOT NULL DEFAULT FALSE,
    model_improvement BOOLEAN NOT NULL DEFAULT FALSE,
    notice_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_pilot_consent_action CHECK (action IN ('accepted', 'updated', 'withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_pilot_consent_participant_created
    ON pilot_consents (participant_id, created_at);

CREATE TABLE IF NOT EXISTS pilot_feedback (
    id VARCHAR(36) PRIMARY KEY,
    participant_id VARCHAR(36) NOT NULL REFERENCES pilot_participants(id) ON DELETE CASCADE,
    category VARCHAR(32) NOT NULL,
    rating INTEGER NOT NULL,
    context VARCHAR(160) NOT NULL DEFAULT 'pilot_hub',
    message TEXT NOT NULL,
    allow_follow_up BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_pilot_feedback_category CHECK (
        category IN ('usability', 'trust', 'recommendation', 'bug', 'other')
    ),
    CONSTRAINT ck_pilot_feedback_rating CHECK (rating >= 1 AND rating <= 5)
);
CREATE INDEX IF NOT EXISTS ix_pilot_feedback_participant_created
    ON pilot_feedback (participant_id, created_at);

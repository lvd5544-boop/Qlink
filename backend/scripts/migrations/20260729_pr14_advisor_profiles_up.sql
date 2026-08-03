-- PR14 four-layer target-role profiles, governed source versions, and advisor traces

ALTER TABLE data_sources
    ADD COLUMN IF NOT EXISTS scope JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE data_source_versions
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending_validation';

DO $constraint$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_data_source_version_status'
    ) THEN
        ALTER TABLE data_source_versions
            ADD CONSTRAINT ck_data_source_version_status CHECK (
                status IN ('pending_validation', 'published', 'superseded', 'revoked')
            );
    END IF;
END
$constraint$;

CREATE TABLE IF NOT EXISTS target_role_profile_snapshots (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    jd_snapshot_hash VARCHAR(64) NOT NULL,
    snapshot_hash VARCHAR(64) NOT NULL,
    profile_schema_version VARCHAR(64) NOT NULL,
    parser_version VARCHAR(64) NOT NULL,
    rule_version VARCHAR(64) NOT NULL,
    model_version VARCHAR(128),
    taxonomy_version VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    occupation_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    company_context_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    market_signal_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_manifest JSONB NOT NULL DEFAULT '[]'::jsonb,
    freshness_expires_at TIMESTAMPTZ,
    confirmed_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_target_role_profile_status CHECK (
        status IN ('draft', 'employer_confirmed', 'superseded')
    ),
    CONSTRAINT uq_target_role_profile_job_hash UNIQUE (job_id, snapshot_hash)
);
CREATE INDEX IF NOT EXISTS ix_target_role_profile_job_status
    ON target_role_profile_snapshots (job_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS job_requirements (
    id VARCHAR(36) PRIMARY KEY,
    profile_snapshot_id VARCHAR(36) NOT NULL
        REFERENCES target_role_profile_snapshots(id) ON DELETE CASCADE,
    requirement_type VARCHAR(32) NOT NULL,
    raw_text TEXT NOT NULL,
    canonical_id VARCHAR(160),
    canonical_label VARCHAR(255),
    importance INTEGER NOT NULL DEFAULT 50,
    requirement_level VARCHAR(24) NOT NULL DEFAULT 'required',
    is_hard_constraint BOOLEAN NOT NULL DEFAULT FALSE,
    employer_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    source_offset JSONB,
    source_id VARCHAR(128),
    source_version_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_job_requirement_type CHECK (
        requirement_type IN (
            'task','skill','experience','education','certificate',
            'location','salary','work_mode','other'
        )
    ),
    CONSTRAINT ck_job_requirement_level CHECK (
        requirement_level IN ('required','preferred','context')
    )
);
CREATE INDEX IF NOT EXISTS ix_job_requirements_snapshot
    ON job_requirements (profile_snapshot_id, requirement_type, importance DESC);

CREATE TABLE IF NOT EXISTS advisor_messages (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    profile_snapshot_id VARCHAR(36) NOT NULL
        REFERENCES target_role_profile_snapshots(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    statements JSONB NOT NULL DEFAULT '[]'::jsonb,
    response_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_version VARCHAR(64),
    model_version VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_advisor_message_role CHECK (role IN ('user', 'advisor'))
);
CREATE INDEX IF NOT EXISTS ix_advisor_messages_user_job
    ON advisor_messages (user_id, job_id, created_at);

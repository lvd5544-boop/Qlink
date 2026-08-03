CREATE TABLE IF NOT EXISTS career_experiences (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    experience_type VARCHAR(24) NOT NULL,
    organization VARCHAR(255),
    title VARCHAR(255),
    start_date DATE,
    end_date DATE,
    date_precision VARCHAR(16) NOT NULL DEFAULT 'unknown',
    description TEXT,
    source_kind VARCHAR(32) NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    workflow_state VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_career_experience_type CHECK (experience_type IN ('work','project','education','volunteer','freelance','award','other')),
    CONSTRAINT ck_career_experience_precision CHECK (date_precision IN ('day','month','year','unknown')),
    CONSTRAINT ck_career_experience_state CHECK (workflow_state IN ('active','archived','withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_career_experiences_user_time ON career_experiences (user_id, start_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id VARCHAR(36) PRIMARY KEY,
    owner_user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artifact_type VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    object_ref TEXT,
    source_url TEXT,
    content_hash VARCHAR(64),
    mime_type VARCHAR(255),
    size_bytes BIGINT,
    extracted_text_ref TEXT,
    issuer VARCHAR(255),
    occurred_at TIMESTAMPTZ,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'user_provided',
    verification_ref TEXT,
    allowed_uses JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_visibility VARCHAR(32) NOT NULL DEFAULT 'private',
    retention_until TIMESTAMPTZ,
    withdrawn_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_evidence_artifact_type CHECK (artifact_type IN ('document','link','code','sample','certificate','image','user_statement','other')),
    CONSTRAINT ck_evidence_artifact_verification CHECK (verification_status IN ('user_provided','third_party_verified','rejected','withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_evidence_artifacts_owner_created ON evidence_artifacts (owner_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS resume_versions (
    id VARCHAR(36) PRIMARY KEY,
    resume_id VARCHAR(36) NOT NULL REFERENCES resumes(id) ON DELETE RESTRICT,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    parsed_json_snapshot JSONB NOT NULL,
    raw_text_snapshot TEXT,
    content_hash VARCHAR(64) NOT NULL,
    created_reason VARCHAR(32) NOT NULL,
    parent_version_id VARCHAR(36) REFERENCES resume_versions(id) ON DELETE SET NULL,
    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_resume_version_number UNIQUE (resume_id, version_number)
);
CREATE INDEX IF NOT EXISTS ix_resume_versions_user_created ON resume_versions (user_id, created_at DESC);

ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS career_experience_id VARCHAR(36) REFERENCES career_experiences(id) ON DELETE SET NULL;
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS origin_kind VARCHAR(32) NOT NULL DEFAULT 'resume';
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS source_object_type VARCHAR(64);
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS source_object_id VARCHAR(36);
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS source_span JSONB;
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS confirmation_state VARCHAR(24) NOT NULL DEFAULT 'unconfirmed';
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS sensitivity_level VARCHAR(24) NOT NULL DEFAULT 'normal';
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS default_visibility VARCHAR(32) NOT NULL DEFAULT 'private';
ALTER TABLE resume_claims ADD COLUMN IF NOT EXISTS superseded_by_claim_id VARCHAR(36) REFERENCES resume_claims(id) ON DELETE SET NULL;
UPDATE resume_claims AS claim
SET user_id = resume.user_id,
    source_object_type = COALESCE(claim.source_object_type, 'resume'),
    source_object_id = COALESCE(claim.source_object_id, claim.resume_id)
FROM resumes AS resume
WHERE claim.resume_id = resume.id AND claim.user_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_resume_claim_user_state ON resume_claims (user_id, workflow_state, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_resume_claim_experience ON resume_claims (career_experience_id, updated_at DESC);

ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS artifact_id VARCHAR(36) REFERENCES evidence_artifacts(id) ON DELETE SET NULL;
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS relationship VARCHAR(24) NOT NULL DEFAULT 'supports';
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS source_span JSONB;
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS link_created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS link_method VARCHAR(24) NOT NULL DEFAULT 'manual';
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS model_suggestion_id VARCHAR(36);
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS candidate_confirmed BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS access_scope VARCHAR(32) NOT NULL DEFAULT 'private';
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;
ALTER TABLE claim_evidence ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;
UPDATE claim_evidence SET link_created_by = provided_by WHERE link_created_by IS NULL;
CREATE INDEX IF NOT EXISTS ix_claim_evidence_artifact ON claim_evidence (artifact_id, created_at DESC);

CREATE TABLE IF NOT EXISTS resume_version_claim_links (
    id VARCHAR(36) PRIMARY KEY,
    resume_version_id VARCHAR(36) NOT NULL REFERENCES resume_versions(id) ON DELETE CASCADE,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE RESTRICT,
    claim_revision_id VARCHAR(36) REFERENCES claim_revisions(id) ON DELETE SET NULL,
    field_path VARCHAR(255) NOT NULL,
    text_snapshot TEXT NOT NULL,
    evidence_ids_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
    fidelity_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_resume_version_claim_field UNIQUE (resume_version_id, claim_id, field_path)
);

CREATE TABLE IF NOT EXISTS migration_orphan_reports (
    id VARCHAR(36) PRIMARY KEY,
    migration_version VARCHAR(128) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(36) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_migration_orphan UNIQUE (migration_version, entity_type, entity_id)
);
INSERT INTO migration_orphan_reports (id, migration_version, entity_type, entity_id, reason)
SELECT md5('pr11:' || id), '20260728_pr11_career_passport_vault', 'resume_claim', id, '无法从 Resume 回填 owner；原记录保留'
FROM resume_claims
WHERE user_id IS NULL
ON CONFLICT (migration_version, entity_type, entity_id) DO NOTHING;

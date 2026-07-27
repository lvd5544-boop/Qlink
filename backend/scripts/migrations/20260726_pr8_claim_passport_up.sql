-- PR8 Claim Passport: provenance, evidence, revisions and immutable application snapshots.
CREATE TABLE IF NOT EXISTS resume_claims (
    id VARCHAR(36) PRIMARY KEY,
    resume_id VARCHAR(36) NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    source_key VARCHAR(160) NOT NULL,
    section VARCHAR(64) NOT NULL,
    item_index INTEGER,
    field_path VARCHAR(255) NOT NULL,
    claim_type VARCHAR(48) NOT NULL,
    original_text TEXT NOT NULL,
    current_text TEXT NOT NULL,
    evidence_state VARCHAR(48) NOT NULL DEFAULT 'not_enough_information',
    workflow_state VARCHAR(24) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_resume_claim_source_key UNIQUE (resume_id, source_key),
    CONSTRAINT ck_resume_claim_evidence_state CHECK (evidence_state IN ('supported_by_user_evidence', 'not_enough_information', 'conflict_detected')),
    CONSTRAINT ck_resume_claim_workflow_state CHECK (workflow_state IN ('open', 'answered', 'reviewed', 'withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_resume_claim_resume_state ON resume_claims (resume_id, workflow_state, updated_at DESC);

CREATE TABLE IF NOT EXISTS claim_evidence (
    id VARCHAR(36) PRIMARY KEY,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE CASCADE,
    evidence_type VARCHAR(32) NOT NULL,
    summary TEXT,
    source TEXT,
    provided_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'user_provided',
    withdrawn_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_claim_evidence_type CHECK (evidence_type IN ('user_statement', 'metric_context', 'document_reference', 'employer_review')),
    CONSTRAINT ck_claim_evidence_verification_status CHECK (verification_status IN ('user_provided', 'employer_reviewed', 'withdrawn'))
);
CREATE INDEX IF NOT EXISTS ix_claim_evidence_claim_created ON claim_evidence (claim_id, created_at DESC);

CREATE TABLE IF NOT EXISTS claim_revisions (
    id VARCHAR(36) PRIMARY KEY,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE CASCADE,
    before_text TEXT NOT NULL,
    after_text TEXT NOT NULL,
    rewrite_mode VARCHAR(48),
    evidence_ids JSONB,
    model_version VARCHAR(128),
    prompt_version VARCHAR(128),
    rule_version VARCHAR(128),
    fidelity_result JSONB,
    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_claim_revision_claim_created ON claim_revisions (claim_id, created_at DESC);

CREATE TABLE IF NOT EXISTS claim_application_links (
    id VARCHAR(36) PRIMARY KEY,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE RESTRICT,
    application_id VARCHAR(36) NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
    text_snapshot TEXT NOT NULL,
    evidence_state_snapshot VARCHAR(48) NOT NULL,
    workflow_state_snapshot VARCHAR(24) NOT NULL,
    audit_snapshot JSONB,
    employer_reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_claim_application_link UNIQUE (claim_id, application_id)
);
CREATE INDEX IF NOT EXISTS ix_claim_application_link_application ON claim_application_links (application_id, created_at DESC);

CREATE TABLE IF NOT EXISTS claim_events (
    id VARCHAR(36) PRIMARY KEY,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE RESTRICT,
    event_type VARCHAR(64) NOT NULL,
    actor_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_claim_event_claim_created ON claim_events (claim_id, created_at DESC);

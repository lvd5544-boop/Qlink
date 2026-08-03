-- PR15 senior-HR batch screening, decision traces, immutable execute snapshots

CREATE TABLE IF NOT EXISTS decision_traces (
    id VARCHAR(36) PRIMARY KEY,
    decision_type VARCHAR(64) NOT NULL,
    subject_type VARCHAR(64) NOT NULL,
    subject_id VARCHAR(36) NOT NULL,
    observed_source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    rules_fired JSONB NOT NULL DEFAULT '[]'::jsonb,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    alternative_explanations JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainties JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_next_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    human_review_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_decision_traces_subject
    ON decision_traces (subject_type, subject_id, created_at DESC);

CREATE TABLE IF NOT EXISTS screening_runs (
    id VARCHAR(36) PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    employer_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_snapshot_id VARCHAR(36) NOT NULL
        REFERENCES target_role_profile_snapshots(id) ON DELETE RESTRICT,
    profile_snapshot_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    candidate_count INTEGER NOT NULL DEFAULT 0,
    rules_version VARCHAR(64) NOT NULL DEFAULT 'screening_rules_v1',
    keyword_version VARCHAR(64) NOT NULL DEFAULT 'keyword_v1',
    model_version VARCHAR(128),
    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_screening_run_status CHECK (
        status IN ('draft', 'configured', 'running', 'completed', 'failed')
    )
);
CREATE INDEX IF NOT EXISTS ix_screening_runs_employer_job
    ON screening_runs (employer_id, job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS screening_rules (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
    rule_type VARCHAR(32) NOT NULL,
    field VARCHAR(64) NOT NULL,
    operator VARCHAR(32) NOT NULL,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    job_requirement_id VARCHAR(36) REFERENCES job_requirements(id) ON DELETE RESTRICT,
    employer_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    legal_basis_note TEXT,
    order_no INTEGER NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_screening_rule_type CHECK (
        rule_type IN ('hard_constraint', 'keyword', 'taxonomy')
    )
);
CREATE INDEX IF NOT EXISTS ix_screening_rules_run_order
    ON screening_rules (run_id, order_no, created_at);

CREATE TABLE IF NOT EXISTS screening_results (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES screening_runs(id) ON DELETE CASCADE,
    application_id VARCHAR(36) NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
    hard_filter_status VARCHAR(16) NOT NULL,
    hard_filter_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    keyword_hits JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
    gap_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    consistency_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    alternative_explanations JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested_followups JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    resume_version_id VARCHAR(128),
    resume_content_hash VARCHAR(128) NOT NULL,
    requirement_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    claim_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_trace_id VARCHAR(36) REFERENCES decision_traces(id) ON DELETE SET NULL,
    reviewer_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_screening_result_run_application UNIQUE (run_id, application_id),
    CONSTRAINT ck_screening_hard_filter CHECK (
        hard_filter_status IN ('pass', 'fail', 'unknown')
    ),
    CONSTRAINT ck_screening_result_status CHECK (
        status IN ('pending_review', 'reviewed', 'clarification_requested')
    )
);
CREATE INDEX IF NOT EXISTS ix_screening_results_run_status
    ON screening_results (run_id, status, created_at);

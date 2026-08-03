-- PR13 target-job diagnostics, faithful rewrite proposals and readiness actions

CREATE TABLE IF NOT EXISTS optimization_issues (
    id VARCHAR(36) PRIMARY KEY,
    diagnostic_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id VARCHAR(36) NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    resume_version_id VARCHAR(36) NOT NULL REFERENCES resume_versions(id) ON DELETE CASCADE,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    profile_snapshot_id VARCHAR(36),
    issue_key VARCHAR(160) NOT NULL,
    issue_type VARCHAR(64) NOT NULL,
    target_requirement_id VARCHAR(160),
    diagnosis TEXT NOT NULL,
    severity VARCHAR(16) NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    rule_version VARCHAR(64) NOT NULL,
    model_version VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_optimization_issue_severity CHECK (
        severity IN ('blocker', 'high', 'medium', 'low')
    ),
    CONSTRAINT ck_optimization_issue_status CHECK (
        status IN ('open', 'resolved', 'dismissed', 'superseded')
    )
);
CREATE INDEX IF NOT EXISTS ix_optimization_issues_diagnostic
    ON optimization_issues (diagnostic_id, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_optimization_issues_resume_job
    ON optimization_issues (resume_id, job_id, status);

CREATE TABLE IF NOT EXISTS optimization_issue_claim_links (
    id VARCHAR(36) PRIMARY KEY,
    issue_id VARCHAR(36) NOT NULL REFERENCES optimization_issues(id) ON DELETE CASCADE,
    claim_id VARCHAR(36) NOT NULL REFERENCES resume_claims(id) ON DELETE RESTRICT,
    relation VARCHAR(24) NOT NULL DEFAULT 'related',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_optimization_issue_claim_relation UNIQUE (issue_id, claim_id, relation)
);

CREATE TABLE IF NOT EXISTS optimization_strategy_options (
    id VARCHAR(36) PRIMARY KEY,
    issue_id VARCHAR(36) NOT NULL REFERENCES optimization_issues(id) ON DELETE CASCADE,
    strategy VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    why TEXT NOT NULL,
    requires_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    can_apply_now BOOLEAN NOT NULL DEFAULT FALSE,
    next_action VARCHAR(64) NOT NULL,
    affected_dimensions JSONB NOT NULL DEFAULT '[]'::jsonb,
    time_horizon VARCHAR(32) NOT NULL,
    user_cost VARCHAR(32) NOT NULL,
    hallucination_risk VARCHAR(16) NOT NULL DEFAULT 'low',
    recommended BOOLEAN NOT NULL DEFAULT FALSE,
    eligibility_reason TEXT NOT NULL,
    counterfactual_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    expression_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
    evidence_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
    capability_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL DEFAULT 'available',
    rule_version VARCHAR(64) NOT NULL,
    scoring_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_optimization_strategy_status CHECK (
        status IN ('available', 'selected', 'rejected', 'superseded')
    )
);
CREATE INDEX IF NOT EXISTS ix_optimization_strategies_issue
    ON optimization_strategy_options (issue_id, recommended);

CREATE TABLE IF NOT EXISTS readiness_actions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    issue_id VARCHAR(36) NOT NULL REFERENCES optimization_issues(id) ON DELETE CASCADE,
    strategy_id VARCHAR(36) NOT NULL REFERENCES optimization_strategy_options(id) ON DELETE CASCADE,
    action_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'planned',
    completion_evidence_id VARCHAR(36) REFERENCES evidence_artifacts(id) ON DELETE SET NULL,
    expected_time_horizon VARCHAR(32) NOT NULL,
    user_cost VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_readiness_action_status CHECK (
        status IN ('planned', 'in_progress', 'completed', 'abandoned')
    )
);
CREATE INDEX IF NOT EXISTS ix_readiness_actions_user_job
    ON readiness_actions (user_id, job_id, status);

CREATE TABLE IF NOT EXISTS resume_patch_proposals (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id VARCHAR(36) NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    resume_version_id VARCHAR(36) NOT NULL REFERENCES resume_versions(id) ON DELETE CASCADE,
    target_job_id VARCHAR(36) NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    issue_id VARCHAR(36) NOT NULL REFERENCES optimization_issues(id) ON DELETE CASCADE,
    strategy_id VARCHAR(36) NOT NULL REFERENCES optimization_strategy_options(id) ON DELETE CASCADE,
    field_path VARCHAR(255) NOT NULL,
    before_text TEXT NOT NULL,
    after_text TEXT NOT NULL,
    atomic_changes JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_claim_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_answer_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    fidelity_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    prompt_version VARCHAR(64),
    model_version VARCHAR(128),
    rule_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMPTZ,
    applied_resume_version_id VARCHAR(36) REFERENCES resume_versions(id) ON DELETE SET NULL,
    CONSTRAINT ck_resume_patch_status CHECK (
        status IN ('draft', 'needs_confirmation', 'ready', 'applied', 'rejected', 'expired')
    )
);
CREATE INDEX IF NOT EXISTS ix_resume_patch_resume_job
    ON resume_patch_proposals (resume_id, target_job_id, status);

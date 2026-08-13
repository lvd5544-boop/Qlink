-- C5 bounded inference hypotheses. These rows are not resume Claims or hiring conclusions.

CREATE TABLE IF NOT EXISTS inference_hypotheses (
    id VARCHAR(36) PRIMARY KEY,
    issue_id VARCHAR(36) NOT NULL REFERENCES optimization_issues(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hypothesis_key VARCHAR(160) NOT NULL,
    text TEXT NOT NULL,
    validation_question TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'hypothesis',
    validation_evidence_id VARCHAR(36) REFERENCES evidence_artifacts(id) ON DELETE SET NULL,
    rule_version VARCHAR(64) NOT NULL,
    prompt_version VARCHAR(64),
    model_version VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validated_at TIMESTAMPTZ,
    CONSTRAINT ck_inference_hypothesis_status CHECK (
        status IN ('hypothesis', 'user_confirmed', 'evidence_supported', 'rejected')
    ),
    CONSTRAINT uq_inference_hypothesis_issue_key UNIQUE (issue_id, hypothesis_key)
);
CREATE INDEX IF NOT EXISTS ix_inference_hypotheses_issue_status
    ON inference_hypotheses (issue_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_inference_hypotheses_user_status
    ON inference_hypotheses (user_id, status, created_at);

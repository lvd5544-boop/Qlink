-- PR12 structured interview sessions / questions / answers / observations

CREATE TABLE IF NOT EXISTS interview_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode VARCHAR(32) NOT NULL,
    job_id VARCHAR(36) REFERENCES job_descriptions(id) ON DELETE SET NULL,
    resume_id VARCHAR(36) REFERENCES resumes(id) ON DELETE SET NULL,
    claim_id VARCHAR(36) REFERENCES resume_claims(id) ON DELETE SET NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    consent_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version VARCHAR(64) NOT NULL DEFAULT 'interview_policy_v1',
    rubric_version VARCHAR(64) NOT NULL DEFAULT 'interview_rubric_v1',
    prompt_version VARCHAR(64) NOT NULL DEFAULT 'interview_prompt_v1',
    model_version VARCHAR(64),
    ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT ck_interview_session_mode CHECK (
        mode IN ('vault_builder', 'target_gap', 'claim_clarification', 'practice')
    ),
    CONSTRAINT ck_interview_session_status CHECK (
        status IN ('active', 'completed', 'revoked')
    )
);
CREATE INDEX IF NOT EXISTS ix_interview_sessions_user_status
    ON interview_sessions (user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_interview_sessions_claim
    ON interview_sessions (claim_id);

CREATE TABLE IF NOT EXISTS interview_questions (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    question_goal VARCHAR(64) NOT NULL,
    claim_id VARCHAR(36) REFERENCES resume_claims(id) ON DELETE SET NULL,
    requirement_id VARCHAR(128),
    competency_id VARCHAR(128),
    core_or_probe VARCHAR(16) NOT NULL DEFAULT 'core',
    question_text TEXT NOT NULL,
    policy_version VARCHAR(64) NOT NULL DEFAULT 'interview_policy_v1',
    generated_by VARCHAR(32) NOT NULL DEFAULT 'rules',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_interview_question_seq UNIQUE (session_id, sequence_no),
    CONSTRAINT ck_interview_question_core_or_probe CHECK (
        core_or_probe IN ('core', 'probe')
    )
);
CREATE INDEX IF NOT EXISTS ix_interview_questions_session
    ON interview_questions (session_id, sequence_no);

CREATE TABLE IF NOT EXISTS interview_answers (
    id VARCHAR(36) PRIMARY KEY,
    question_id VARCHAR(36) NOT NULL REFERENCES interview_questions(id) ON DELETE CASCADE,
    raw_answer_ref VARCHAR(255),
    answer_text_snapshot TEXT NOT NULL DEFAULT '',
    user_declined BOOLEAN NOT NULL DEFAULT FALSE,
    decline_reason VARCHAR(64),
    confirmed_at TIMESTAMPTZ,
    allowed_uses JSONB NOT NULL DEFAULT '{}'::jsonb,
    share_with_employer BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_interview_answer_question UNIQUE (question_id)
);
CREATE INDEX IF NOT EXISTS ix_interview_answers_question
    ON interview_answers (question_id);

CREATE TABLE IF NOT EXISTS interview_observations (
    id VARCHAR(36) PRIMARY KEY,
    answer_id VARCHAR(36) NOT NULL REFERENCES interview_answers(id) ON DELETE CASCADE,
    observation_type VARCHAR(32) NOT NULL,
    text TEXT NOT NULL,
    source_start INTEGER NOT NULL,
    source_end INTEGER NOT NULL,
    claim_id VARCHAR(36) REFERENCES resume_claims(id) ON DELETE SET NULL,
    candidate_confirmation_state VARCHAR(32) NOT NULL DEFAULT 'pending',
    extractor_version VARCHAR(64) NOT NULL DEFAULT 'rules_obs_v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_interview_observation_type CHECK (
        observation_type IN (
            'situation', 'task', 'candidate_action', 'team_action', 'method',
            'result', 'metric', 'evidence', 'reflection', 'preference', 'constraint'
        )
    ),
    CONSTRAINT ck_interview_observation_confirm CHECK (
        candidate_confirmation_state IN ('pending', 'confirmed', 'rejected')
    )
);
CREATE INDEX IF NOT EXISTS ix_interview_observations_answer
    ON interview_observations (answer_id, candidate_confirmation_state);

ALTER TABLE interview_results
    ADD COLUMN IF NOT EXISTS structured_session_id VARCHAR(36)
        REFERENCES interview_sessions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_interview_results_structured_session
    ON interview_results (structured_session_id);

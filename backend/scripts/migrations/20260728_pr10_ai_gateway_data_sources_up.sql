CREATE TABLE IF NOT EXISTS data_sources (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_organization VARCHAR(255),
    acquisition_method VARCHAR(64) NOT NULL DEFAULT 'manual',
    license_name VARCHAR(255),
    license_url TEXT,
    contract_ref TEXT,
    allowed_product_uses JSONB NOT NULL DEFAULT '[]'::jsonb,
    training_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    contains_personal_data BOOLEAN NOT NULL DEFAULT FALSE,
    processing_region VARCHAR(64) NOT NULL DEFAULT 'cn-beijing',
    attribution_text TEXT,
    deletion_contact TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    layer VARCHAR(8) NOT NULL DEFAULT 'E',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_data_sources_status CHECK (
        status IN ('pending_review', 'approved', 'restricted', 'revoked')
    ),
    CONSTRAINT ck_data_sources_layer CHECK (
        layer IN ('A', 'B', 'C', 'D', 'E')
    )
);
CREATE INDEX IF NOT EXISTS ix_data_sources_status_layer
    ON data_sources (status, layer);

CREATE TABLE IF NOT EXISTS data_source_versions (
    id VARCHAR(36) PRIMARY KEY,
    source_id VARCHAR(36) NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    external_version VARCHAR(128) NOT NULL,
    retrieved_at TIMESTAMPTZ,
    effective_at TIMESTAMPTZ,
    checksum VARCHAR(128),
    raw_object_ref TEXT,
    parser_version VARCHAR(64),
    expires_at TIMESTAMPTZ,
    validation_report JSONB,
    superseded_by_version_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_data_source_versions_source
    ON data_source_versions (source_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_invocations (
    id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model_alias VARCHAR(128),
    model_id VARCHAR(128) NOT NULL,
    prompt_version VARCHAR(64),
    schema_version VARCHAR(64),
    input_snapshot_hash VARCHAR(128) NOT NULL,
    data_region VARCHAR(64) NOT NULL DEFAULT 'cn-beijing',
    token_input INTEGER,
    token_output INTEGER,
    cost_microunits BIGINT,
    latency_ms INTEGER,
    status VARCHAR(32) NOT NULL,
    error_category VARCHAR(64),
    user_id VARCHAR(36),
    org_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_ai_invocations_status CHECK (
        status IN ('succeeded', 'failed', 'canceled', 'skipped', 'unknown')
    )
);
CREATE INDEX IF NOT EXISTS ix_ai_invocations_created_task
    ON ai_invocations (created_at DESC, task_type);

-- Seed forum statistical source as layer E (not usable for formal profiles).
INSERT INTO data_sources (
    id, name, owner_organization, acquisition_method, license_name,
    allowed_product_uses, training_allowed, contains_personal_data,
    processing_region, attribution_text, status, layer
) VALUES (
    'ds_forum_statistical',
    '网络录用经验（论坛统计）',
    'platform',
    'public_forum_scrape',
    'public_web_terms',
    '["qualitative_clue"]'::jsonb,
    FALSE,
    FALSE,
    'cn-beijing',
    'Reddit / V2EX / Hacker News public posts - non-representative.',
    'restricted',
    'E'
) ON CONFLICT (id) DO NOTHING;

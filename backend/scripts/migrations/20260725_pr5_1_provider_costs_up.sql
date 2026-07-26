CREATE TABLE IF NOT EXISTS provider_cost_events (
    id VARCHAR(36) PRIMARY KEY,
    reservation_id VARCHAR(36)
        REFERENCES usage_reservations(id) ON DELETE SET NULL,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    organization_id VARCHAR(36)
        REFERENCES organizations(id) ON DELETE SET NULL,
    feature VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    model_version VARCHAR(64),
    prompt_version VARCHAR(64),
    provider_request_id VARCHAR(255),
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
    cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL,
    cost_microunits INTEGER NOT NULL DEFAULT 0,
    cost_minor_units INTEGER NOT NULL DEFAULT 0,
    price_version VARCHAR(64) NOT NULL,
    provider_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_provider_cost_request
        UNIQUE (provider, provider_request_id),
    CONSTRAINT ck_provider_cost_nonnegative_tokens
        CHECK (
            input_tokens >= 0
            AND output_tokens >= 0
            AND cache_hit_tokens >= 0
            AND cache_miss_tokens >= 0
        ),
    CONSTRAINT ck_provider_cost_nonnegative_amount
        CHECK (cost_microunits >= 0 AND cost_minor_units >= 0),
    CONSTRAINT ck_provider_cost_status
        CHECK (provider_status IN ('succeeded', 'failed', 'canceled', 'unknown'))
);

CREATE INDEX IF NOT EXISTS ix_provider_cost_created_feature
    ON provider_cost_events (created_at, feature);

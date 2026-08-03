CREATE TABLE IF NOT EXISTS api_idempotency_keys (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope VARCHAR(96) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    CONSTRAINT uq_api_idempotency_user_scope_key UNIQUE (user_id, scope, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_api_idempotency_expires
    ON api_idempotency_keys (expires_at);

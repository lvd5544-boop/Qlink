CREATE TABLE IF NOT EXISTS usage_reservations (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    feature VARCHAR(64) NOT NULL,
    month_key VARCHAR(7) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    reserved_units INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(16) NOT NULL DEFAULT 'reserved',
    estimated_cost_usd DOUBLE PRECISION DEFAULT 0,
    meta JSON,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_usage_reservation_idempotency
        UNIQUE (user_id, feature, month_key, idempotency_key),
    CONSTRAINT ck_usage_reservation_status
        CHECK (status IN ('reserved', 'succeeded', 'failed', 'released'))
);

CREATE INDEX IF NOT EXISTS ix_usage_reservation_quota
    ON usage_reservations (user_id, feature, month_key, status);

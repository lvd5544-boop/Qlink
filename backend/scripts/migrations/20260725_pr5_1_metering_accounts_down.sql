DROP INDEX IF EXISTS ix_usage_reservation_quota;
ALTER TABLE usage_reservations
    DROP CONSTRAINT IF EXISTS uq_usage_reservation_account_attempt;
ALTER TABLE usage_reservations
    DROP CONSTRAINT IF EXISTS ck_usage_reservation_status;

ALTER TABLE usage_reservations
    ADD CONSTRAINT uq_usage_reservation_idempotency
    UNIQUE (user_id, feature, month_key, idempotency_key);
ALTER TABLE usage_reservations
    ADD CONSTRAINT ck_usage_reservation_status
    CHECK (status IN ('reserved', 'succeeded', 'failed', 'released'));

CREATE INDEX IF NOT EXISTS ix_usage_reservation_quota
    ON usage_reservations (user_id, feature, month_key, status);

ALTER TABLE usage_reservations DROP COLUMN IF EXISTS finalized_at;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS model_called;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS error_code;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS attempt;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS request_fingerprint;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS period_key;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS billing_account_id;
ALTER TABLE usage_reservations DROP COLUMN IF EXISTS billing_account_type;

ALTER TABLE usage_events DROP COLUMN IF EXISTS period_key;
ALTER TABLE usage_events DROP COLUMN IF EXISTS billing_account_id;
ALTER TABLE usage_events DROP COLUMN IF EXISTS billing_account_type;

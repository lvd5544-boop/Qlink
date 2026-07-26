ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS billing_account_type VARCHAR(20);
ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS billing_account_id VARCHAR(36);
ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS period_key VARCHAR(32);

UPDATE usage_events
SET billing_account_type = 'user',
    billing_account_id = user_id,
    period_key = month_key
WHERE billing_account_type IS NULL
   OR billing_account_id IS NULL
   OR period_key IS NULL;

ALTER TABLE usage_events
    ALTER COLUMN billing_account_type SET NOT NULL;
ALTER TABLE usage_events
    ALTER COLUMN billing_account_id SET NOT NULL;
ALTER TABLE usage_events
    ALTER COLUMN period_key SET NOT NULL;

ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS billing_account_type VARCHAR(20);
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS billing_account_id VARCHAR(36);
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS period_key VARCHAR(32);
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS request_fingerprint VARCHAR(64);
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 1;
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(64);
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS model_called BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usage_reservations
    ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ;

UPDATE usage_reservations
SET billing_account_type = 'user',
    billing_account_id = user_id,
    period_key = month_key,
    request_fingerprint = COALESCE(
        request_fingerprint,
        md5(feature || ':' || idempotency_key)
    ),
    status = CASE WHEN status = 'failed' THEN 'released' ELSE status END
WHERE billing_account_type IS NULL
   OR billing_account_id IS NULL
   OR period_key IS NULL
   OR request_fingerprint IS NULL
   OR status = 'failed';

ALTER TABLE usage_reservations
    ALTER COLUMN billing_account_type SET NOT NULL;
ALTER TABLE usage_reservations
    ALTER COLUMN billing_account_id SET NOT NULL;
ALTER TABLE usage_reservations
    ALTER COLUMN period_key SET NOT NULL;
ALTER TABLE usage_reservations
    ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE usage_reservations
    DROP CONSTRAINT IF EXISTS uq_usage_reservation_idempotency;
ALTER TABLE usage_reservations
    DROP CONSTRAINT IF EXISTS uq_usage_reservation_account_attempt;
ALTER TABLE usage_reservations
    DROP CONSTRAINT IF EXISTS ck_usage_reservation_status;
DROP INDEX IF EXISTS ix_usage_reservation_quota;

ALTER TABLE usage_reservations
    ADD CONSTRAINT uq_usage_reservation_account_attempt
    UNIQUE (
        billing_account_type,
        billing_account_id,
        feature,
        period_key,
        idempotency_key,
        attempt
    );
ALTER TABLE usage_reservations
    ADD CONSTRAINT ck_usage_reservation_status
    CHECK (status IN ('reserved', 'succeeded', 'released'));

CREATE INDEX IF NOT EXISTS ix_usage_reservation_quota
    ON usage_reservations (
        billing_account_type,
        billing_account_id,
        feature,
        period_key,
        status
    );

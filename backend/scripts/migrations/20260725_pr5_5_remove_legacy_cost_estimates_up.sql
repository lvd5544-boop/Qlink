ALTER TABLE usage_events
    DROP COLUMN IF EXISTS estimated_cost_usd;

ALTER TABLE usage_reservations
    DROP COLUMN IF EXISTS estimated_cost_usd;

DROP INDEX IF EXISTS ix_provider_cost_created_feature;

-- Intentionally retain provider_cost_events and its audit rows on downgrade.
-- A later forward migration may recreate the query index without losing costs.

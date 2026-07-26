-- Safe compatibility downgrade.
--
-- usage_reservations is now referenced by immutable provider_cost_events.
-- Dropping it would either fail on the foreign key or require CASCADE and
-- destroy the audit chain. The table and its rows are therefore retained.
SELECT 1;

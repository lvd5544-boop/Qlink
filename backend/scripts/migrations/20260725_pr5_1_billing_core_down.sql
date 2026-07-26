DROP TABLE IF EXISTS organization_subscriptions;
DROP TABLE IF EXISTS user_subscriptions;
DROP TABLE IF EXISTS plan_entitlements;
DROP TABLE IF EXISTS plans;
DROP TABLE IF EXISTS organization_memberships;

-- organizations is intentionally retained because provider_cost_events keeps
-- an immutable organization reference. Removing it would require CASCADE and
-- destroy or detach admin cost audit data.

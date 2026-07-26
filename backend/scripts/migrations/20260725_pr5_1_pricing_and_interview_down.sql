DELETE FROM credit_pack_products
WHERE code = 'organization-audit-100-v1';

DELETE FROM plan_entitlements
WHERE plan_code IN (
    'candidate-free-v1',
    'candidate-pro-v1',
    'organization-seat-v1'
);

DELETE FROM plans AS p
WHERE p.code IN (
    'candidate-free-v1',
    'candidate-pro-v1',
    'organization-seat-v1'
)
AND NOT EXISTS (
    SELECT 1 FROM user_subscriptions AS s WHERE s.plan_code = p.code
)
AND NOT EXISTS (
    SELECT 1 FROM organization_subscriptions AS s WHERE s.plan_code = p.code
);

DROP TABLE IF EXISTS interview_usage_sessions;
DROP TABLE IF EXISTS credit_pack_products;

-- Existing user/organization subscriptions and memberships are retained.
-- They are entitlement history and may already be referenced by usage records.

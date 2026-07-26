CREATE TABLE IF NOT EXISTS credit_pack_products (
    code VARCHAR(64) PRIMARY KEY,
    audience VARCHAR(20) NOT NULL,
    name VARCHAR(120) NOT NULL,
    feature VARCHAR(64) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
    price_minor_units INTEGER NOT NULL,
    grant_units INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_credit_pack_audience
        CHECK (audience IN ('candidate', 'organization')),
    CONSTRAINT ck_credit_pack_currency CHECK (currency = 'CNY'),
    CONSTRAINT ck_credit_pack_positive_price CHECK (price_minor_units > 0),
    CONSTRAINT ck_credit_pack_positive_grant CHECK (grant_units > 0),
    CONSTRAINT ck_credit_pack_positive_version CHECK (version >= 1)
);

CREATE TABLE IF NOT EXISTS interview_usage_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    local_day VARCHAR(10) NOT NULL,
    mode VARCHAR(24) NOT NULL,
    turn_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    CONSTRAINT ck_interview_usage_mode
        CHECK (mode IN ('profile', 'claim_followup')),
    CONSTRAINT ck_interview_usage_status
        CHECK (status IN ('active', 'closed', 'abandoned')),
    CONSTRAINT ck_interview_usage_nonnegative_turns CHECK (turn_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_interview_usage_user_day
    ON interview_usage_sessions (user_id, local_day, status);

INSERT INTO plans (
    code, audience, name, currency, price_minor_units,
    billing_period, version, active
) VALUES
    ('candidate-free-v1', 'candidate', 'Candidate Free', 'CNY', 0, 'month', 1, TRUE),
    ('candidate-pro-v1', 'candidate', 'Candidate Pro', 'CNY', 2000, 'month', 1, TRUE),
    ('organization-seat-v1', 'organization', '企业席位', 'CNY', 30000, 'month', 1, TRUE)
ON CONFLICT (code) DO UPDATE SET
    audience = EXCLUDED.audience,
    name = EXCLUDED.name,
    currency = EXCLUDED.currency,
    price_minor_units = EXCLUDED.price_minor_units,
    billing_period = EXCLUDED.billing_period,
    version = EXCLUDED.version,
    active = EXCLUDED.active,
    updated_at = NOW();

INSERT INTO user_subscriptions (
    id, user_id, plan_code, status, period_start, period_end,
    cancel_at_period_end, source
)
SELECT
    'sub-' || SUBSTRING(MD5('candidate-free:' || u.id), 1, 32),
    u.id,
    'candidate-free-v1',
    'active',
    DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Shanghai')
        AT TIME ZONE 'Asia/Shanghai',
    (DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Shanghai')
        + INTERVAL '1 month') AT TIME ZONE 'Asia/Shanghai',
    FALSE,
    'pilot'
FROM users AS u
WHERE u.role = 'candidate'
AND NOT EXISTS (
    SELECT 1
    FROM user_subscriptions AS s
    WHERE s.user_id = u.id
      AND s.status IN ('active', 'trialing')
      AND s.period_end > NOW()
);

INSERT INTO organizations (id, name, status)
SELECT
    'org-' || SUBSTRING(MD5('employer-org:' || u.id), 1, 32),
    COALESCE(NULLIF(u.email, ''), 'Employer ' || SUBSTRING(u.id, 1, 8)),
    'active'
FROM users AS u
WHERE u.role = 'employer'
AND NOT EXISTS (
    SELECT 1
    FROM organization_memberships AS m
    WHERE m.user_id = u.id
      AND m.status IN ('active', 'invited')
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO organization_memberships (
    id, organization_id, user_id, role, status
)
SELECT
    'mem-' || SUBSTRING(MD5('employer-membership:' || u.id), 1, 32),
    'org-' || SUBSTRING(MD5('employer-org:' || u.id), 1, 32),
    u.id,
    'owner',
    'active'
FROM users AS u
WHERE u.role = 'employer'
AND NOT EXISTS (
    SELECT 1
    FROM organization_memberships AS m
    WHERE m.user_id = u.id
      AND m.status IN ('active', 'invited')
)
ON CONFLICT (organization_id, user_id) DO NOTHING;

INSERT INTO organization_subscriptions (
    id, organization_id, plan_code, seat_quantity, status,
    period_start, period_end, cancel_at_period_end, source
)
SELECT
    'sub-' || SUBSTRING(MD5('employer-subscription:' || u.id), 1, 32),
    'org-' || SUBSTRING(MD5('employer-org:' || u.id), 1, 32),
    'organization-seat-v1',
    1,
    'trialing',
    DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Shanghai')
        AT TIME ZONE 'Asia/Shanghai',
    (DATE_TRUNC('month', NOW() AT TIME ZONE 'Asia/Shanghai')
        + INTERVAL '1 month') AT TIME ZONE 'Asia/Shanghai',
    FALSE,
    'pilot'
FROM users AS u
WHERE u.role = 'employer'
AND EXISTS (
    SELECT 1
    FROM organization_memberships AS m
    WHERE m.organization_id =
        'org-' || SUBSTRING(MD5('employer-org:' || u.id), 1, 32)
      AND m.user_id = u.id
)
AND NOT EXISTS (
    SELECT 1
    FROM organization_subscriptions AS s
    WHERE s.organization_id =
        'org-' || SUBSTRING(MD5('employer-org:' || u.id), 1, 32)
      AND s.status IN ('active', 'trialing')
      AND s.period_end > NOW()
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO plan_entitlements (
    id, plan_code, feature, limit_units, period, meter_type
) VALUES
    ('ent-candidate-free-coach-v1', 'candidate-free-v1', 'resume_coach', 50, 'month', 'paid_credit'),
    ('ent-candidate-free-rewrite-v1', 'candidate-free-v1', 'evidence_regenerate', 50, 'month', 'paid_credit'),
    ('ent-candidate-free-interviews-v1', 'candidate-free-v1', 'interview_session', 50, 'day', 'fair_use'),
    ('ent-candidate-free-turns-v1', 'candidate-free-v1', 'interview_turn', 50, 'session', 'fair_use'),
    ('ent-candidate-pro-coach-v1', 'candidate-pro-v1', 'resume_coach', 50, 'month', 'paid_credit'),
    ('ent-candidate-pro-rewrite-v1', 'candidate-pro-v1', 'evidence_regenerate', 50, 'month', 'paid_credit'),
    ('ent-candidate-pro-interviews-v1', 'candidate-pro-v1', 'interview_session', 50, 'day', 'fair_use'),
    ('ent-candidate-pro-turns-v1', 'candidate-pro-v1', 'interview_turn', 50, 'session', 'fair_use'),
    ('ent-organization-audit-v1', 'organization-seat-v1', 'credibility_audit', 300, 'month', 'paid_credit')
ON CONFLICT (plan_code, feature, period) DO UPDATE SET
    limit_units = EXCLUDED.limit_units,
    meter_type = EXCLUDED.meter_type;

INSERT INTO credit_pack_products (
    code, audience, name, feature, currency,
    price_minor_units, grant_units, version, active
) VALUES (
    'organization-audit-100-v1',
    'organization',
    '企业审计 100 Credits',
    'credibility_audit',
    'CNY',
    10000,
    100,
    1,
    TRUE
)
ON CONFLICT (code) DO UPDATE SET
    audience = EXCLUDED.audience,
    name = EXCLUDED.name,
    feature = EXCLUDED.feature,
    currency = EXCLUDED.currency,
    price_minor_units = EXCLUDED.price_minor_units,
    grant_units = EXCLUDED.grant_units,
    version = EXCLUDED.version,
    active = EXCLUDED.active,
    updated_at = NOW();

CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_organization_status
        CHECK (status IN ('active', 'suspended', 'closed'))
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'recruiter',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_organization_membership_user
        UNIQUE (organization_id, user_id),
    CONSTRAINT ck_organization_membership_role
        CHECK (role IN ('owner', 'admin', 'recruiter')),
    CONSTRAINT ck_organization_membership_status
        CHECK (status IN ('active', 'invited', 'disabled'))
);

CREATE INDEX IF NOT EXISTS ix_organization_membership_user_status
    ON organization_memberships (user_id, status);

CREATE TABLE IF NOT EXISTS plans (
    code VARCHAR(64) PRIMARY KEY,
    audience VARCHAR(20) NOT NULL,
    name VARCHAR(120) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
    price_minor_units INTEGER NOT NULL DEFAULT 0,
    billing_period VARCHAR(16) NOT NULL DEFAULT 'month',
    version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_plan_audience
        CHECK (audience IN ('candidate', 'organization')),
    CONSTRAINT ck_plan_currency CHECK (currency = 'CNY'),
    CONSTRAINT ck_plan_billing_period CHECK (billing_period IN ('month')),
    CONSTRAINT ck_plan_nonnegative_price CHECK (price_minor_units >= 0),
    CONSTRAINT ck_plan_positive_version CHECK (version >= 1)
);

CREATE TABLE IF NOT EXISTS plan_entitlements (
    id VARCHAR(36) PRIMARY KEY,
    plan_code VARCHAR(64) NOT NULL REFERENCES plans(code) ON DELETE CASCADE,
    feature VARCHAR(64) NOT NULL,
    limit_units INTEGER,
    period VARCHAR(16) NOT NULL,
    meter_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plan_entitlement_feature_period
        UNIQUE (plan_code, feature, period),
    CONSTRAINT ck_plan_entitlement_period
        CHECK (period IN ('day', 'month', 'session')),
    CONSTRAINT ck_plan_entitlement_meter_type
        CHECK (meter_type IN ('paid_credit', 'fair_use', 'unmetered')),
    CONSTRAINT ck_plan_entitlement_nonnegative_limit
        CHECK (limit_units IS NULL OR limit_units >= 0)
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_code VARCHAR(64) NOT NULL REFERENCES plans(code),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(24) NOT NULL DEFAULT 'pilot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_user_subscription_status
        CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'expired')),
    CONSTRAINT ck_user_subscription_source
        CHECK (source IN ('manual', 'payment_provider', 'pilot')),
    CONSTRAINT ck_user_subscription_period CHECK (period_end > period_start)
);

CREATE INDEX IF NOT EXISTS ix_user_subscription_lookup
    ON user_subscriptions (user_id, status, period_end);

CREATE TABLE IF NOT EXISTS organization_subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL
        REFERENCES organizations(id) ON DELETE CASCADE,
    plan_code VARCHAR(64) NOT NULL REFERENCES plans(code),
    seat_quantity INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(24) NOT NULL DEFAULT 'pilot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_organization_subscription_status
        CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'expired')),
    CONSTRAINT ck_organization_subscription_source
        CHECK (source IN ('manual', 'payment_provider', 'pilot')),
    CONSTRAINT ck_organization_subscription_seats CHECK (seat_quantity >= 1),
    CONSTRAINT ck_organization_subscription_period
        CHECK (period_end > period_start)
);

CREATE INDEX IF NOT EXISTS ix_organization_subscription_lookup
    ON organization_subscriptions (organization_id, status, period_end);

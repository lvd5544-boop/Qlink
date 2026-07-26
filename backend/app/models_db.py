# 修改导入部分，移除 Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Integer,
    String,
    Text,
    Float,
    JSON,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)  # noqa: F401
from sqlalchemy.orm import relationship
from .database import Base

# from pgvector.sqlalchemy import Vector   # 暂时注释掉
import uuid


def _default_user_billing_account(context):
    return str(context.get_current_parameters().get("user_id") or "")


def _default_usage_period(context):
    return str(context.get_current_parameters().get("month_key") or "")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(128), nullable=True)  # 新增
    role = Column(String(20), default="candidate")  # 新增，默认求职者
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resumes = relationship("Resume", back_populates="user")


class Organization(Base):
    """招聘企业的租户、席位和共享计费主体；不同于市场画像 Company。"""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_organization_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationMembership(Base):
    """企业成员与席位占用；一个用户在同一企业只允许一条成员记录。"""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_membership_user",
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'recruiter')",
            name="ck_organization_membership_role",
        ),
        CheckConstraint(
            "status IN ('active', 'invited', 'disabled')",
            name="ck_organization_membership_status",
        ),
        Index(
            "ix_organization_membership_user_status",
            "user_id",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False, default="recruiter")
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization = relationship("Organization")
    user = relationship("User")


class Plan(Base):
    """版本化套餐定义；金额始终以最小货币单位（分）存储。"""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('candidate', 'organization')",
            name="ck_plan_audience",
        ),
        CheckConstraint("currency = 'CNY'", name="ck_plan_currency"),
        CheckConstraint(
            "billing_period IN ('month')",
            name="ck_plan_billing_period",
        ),
        CheckConstraint(
            "price_minor_units >= 0",
            name="ck_plan_nonnegative_price",
        ),
        CheckConstraint("version >= 1", name="ck_plan_positive_version"),
    )

    code = Column(String(64), primary_key=True)
    audience = Column(String(20), nullable=False)
    name = Column(String(120), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY")
    price_minor_units = Column(Integer, nullable=False, default=0)
    billing_period = Column(String(16), nullable=False, default="month")
    version = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlanEntitlement(Base):
    """套餐内按功能和周期定义的额度或 fair-use 权益。"""

    __tablename__ = "plan_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "plan_code",
            "feature",
            "period",
            name="uq_plan_entitlement_feature_period",
        ),
        CheckConstraint(
            "period IN ('day', 'month', 'session')",
            name="ck_plan_entitlement_period",
        ),
        CheckConstraint(
            "meter_type IN ('paid_credit', 'fair_use', 'unmetered')",
            name="ck_plan_entitlement_meter_type",
        ),
        CheckConstraint(
            "limit_units IS NULL OR limit_units >= 0",
            name="ck_plan_entitlement_nonnegative_limit",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_code = Column(
        String(64),
        ForeignKey("plans.code", ondelete="CASCADE"),
        nullable=False,
    )
    feature = Column(String(64), nullable=False)
    limit_units = Column(Integer, nullable=True)
    period = Column(String(16), nullable=False)
    meter_type = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    plan = relationship("Plan")


class CreditPackProduct(Base):
    """一次性加购 credit 商品目录；订单与支付流水由后续支付批次承接。"""

    __tablename__ = "credit_pack_products"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('candidate', 'organization')",
            name="ck_credit_pack_audience",
        ),
        CheckConstraint("currency = 'CNY'", name="ck_credit_pack_currency"),
        CheckConstraint(
            "price_minor_units > 0",
            name="ck_credit_pack_positive_price",
        ),
        CheckConstraint(
            "grant_units > 0",
            name="ck_credit_pack_positive_grant",
        ),
        CheckConstraint("version >= 1", name="ck_credit_pack_positive_version"),
    )

    code = Column(String(64), primary_key=True)
    audience = Column(String(20), nullable=False)
    name = Column(String(120), nullable=False)
    feature = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY")
    price_minor_units = Column(Integer, nullable=False)
    grant_units = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserSubscription(Base):
    """候选人套餐周期；支付渠道接入前允许 manual/pilot 来源。"""

    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'trialing', 'past_due', 'canceled', 'expired')",
            name="ck_user_subscription_status",
        ),
        CheckConstraint(
            "source IN ('manual', 'payment_provider', 'pilot')",
            name="ck_user_subscription_source",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_user_subscription_period",
        ),
        Index(
            "ix_user_subscription_lookup",
            "user_id",
            "status",
            "period_end",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_code = Column(String(64), ForeignKey("plans.code"), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    source = Column(String(24), nullable=False, default="pilot")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User")
    plan = relationship("Plan")


class OrganizationSubscription(Base):
    """企业套餐、购买席位数和共享权益周期。"""

    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'trialing', 'past_due', 'canceled', 'expired')",
            name="ck_organization_subscription_status",
        ),
        CheckConstraint(
            "source IN ('manual', 'payment_provider', 'pilot')",
            name="ck_organization_subscription_source",
        ),
        CheckConstraint(
            "seat_quantity >= 1",
            name="ck_organization_subscription_seats",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_organization_subscription_period",
        ),
        Index(
            "ix_organization_subscription_lookup",
            "organization_id",
            "status",
            "period_end",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_code = Column(String(64), ForeignKey("plans.code"), nullable=False)
    seat_quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="active")
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    source = Column(String(24), nullable=False, default="pilot")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization = relationship("Organization")
    plan = relationship("Plan")


class InterviewUsageSession(Base):
    """免费 AI 面试的 fair-use 会话账，与付费额度账完全分离。"""

    __tablename__ = "interview_usage_sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('profile', 'claim_followup')",
            name="ck_interview_usage_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'closed', 'abandoned')",
            name="ck_interview_usage_status",
        ),
        CheckConstraint(
            "turn_count >= 0",
            name="ck_interview_usage_nonnegative_turns",
        ),
        Index(
            "ix_interview_usage_user_day",
            "user_id",
            "local_day",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_day = Column(String(10), nullable=False)
    mode = Column(String(24), nullable=False)
    turn_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    raw_text = Column(Text, nullable=True)
    parsed_json = Column(JSON, nullable=False)
    health_check = Column(JSON, nullable=True)
    # profile_embedding = Column(Vector(1536), nullable=True)   # 暂时禁用
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="resumes")
    suggestions = relationship("ResumeSuggestion", back_populates="resume")
    variants = relationship("ResumeVariant", back_populates="resume")


class ResumeVariant(Base):
    """岗位定制版简历副本（resume_variants）。"""

    __tablename__ = "resume_variants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    variant_key = Column(String(100), nullable=False)
    label = Column(String(255), nullable=False)
    target_job_title = Column(String(255), nullable=True)
    style_template = Column(String(32), default="balanced")
    parsed_json = Column(JSON, nullable=False)
    source = Column(String(32), default="llm")
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    resume = relationship("Resume", back_populates="variants")
    job = relationship("JobDescription")


class ResumeSuggestion(Base):
    """AI 简历建议（体检 / Coach），记录 pending / applied / dismissed。"""

    __tablename__ = "resume_suggestions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=True)
    source = Column(String(32), default="health_check")  # health_check | coach
    suggestion_key = Column(String(100), nullable=False)
    section = Column(String(50), nullable=True)
    field_path = Column(String(200), nullable=True)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    priority = Column(String(10), default="中")
    issue = Column(Text, nullable=True)
    advice = Column(Text, nullable=True)
    original_text = Column(Text, nullable=True)
    suggested_text = Column(Text, nullable=True)
    section_label = Column(String(100), nullable=True)
    patch = Column(JSON, nullable=True)
    status = Column(String(20), default="pending")  # pending | applied | dismissed
    score_delta = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    resume = relationship("Resume", back_populates="suggestions")
    job = relationship("JobDescription")


class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employer_id = Column(
        String(36), ForeignKey("users.id"), nullable=True
    )  # 简化：招聘方也是 user 表的一条记录
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=True)
    parsed_json = Column(JSON, nullable=False)  # 存储 AI 解析后的结构化岗位
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    employer = relationship("User", backref="job_descriptions")


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint(
            "resume_id",
            "job_id",
            name="uq_match_results_resume_job",
        ),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    score = Column(Float, nullable=False)  # LLM 评分 0-10
    reason = Column(Text, nullable=True)  # 匹配理由
    score_breakdown = Column(JSON, nullable=True)  # 分项得分明细
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resume = relationship("Resume", backref="match_results")
    job = relationship("JobDescription", backref="match_results")


class InterviewInvitation(Base):
    __tablename__ = "interview_invitations"
    __table_args__ = (
        Index(
            "ix_interview_invitations_candidate_status",
            "candidate_id",
            "status",
        ),
        Index(
            "ix_interview_invitations_job_created",
            "job_id",
            "created_at",
        ),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    candidate_id = Column(String(36), ForeignKey("users.id"), nullable=False)  # 求职者 user_id
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=True)  # 关联的简历
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=True)
    status = Column(String(20), default="pending")  # pending / accepted / declined
    message = Column(Text, nullable=True)
    proposed_time = Column(String(255), nullable=True)  # 提议面试时间（如 "2026-05-10 14:00"）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("JobDescription")
    employer = relationship("User", foreign_keys=[employer_id])
    candidate = relationship("User", foreign_keys=[candidate_id])
    resume = relationship("Resume")
    application = relationship("JobApplication", foreign_keys=[application_id])


class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "job_id",
            name="uq_job_applications_candidate_job",
        ),
        Index(
            "ix_job_applications_job_status",
            "job_id",
            "status",
        ),
        Index(
            "ix_job_applications_candidate_created",
            "candidate_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    candidate_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    status = Column(String(20), default="submitted")
    cover_letter = Column(Text, nullable=True)
    # claim_threads / employer_reviewed_at / last_*_activity_at
    pipeline_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("JobDescription")
    employer = relationship("User", foreign_keys=[employer_id])
    candidate = relationship("User", foreign_keys=[candidate_id])
    resume = relationship("Resume")


class ApplicationMessage(Base):
    __tablename__ = "application_messages"
    __table_args__ = (
        Index(
            "ix_application_messages_application_created",
            "application_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=False)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    message_kind = Column(
        String(32), default="text"
    )  # text | clarification_request | clarification_response | interview_summary
    message_meta = Column(JSON, nullable=True)  # claim_id, claim_text, questions 等结构化字段
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("JobApplication", backref="messages")
    sender = relationship("User")


class InterviewResult(Base):
    """User-owned interview artifact; Resume writeback requires confirmation."""

    __tablename__ = "interview_results"
    __table_args__ = (
        UniqueConstraint(
            "fair_use_session_id",
            name="uq_interview_result_fair_use_session",
        ),
        CheckConstraint(
            "mode IN ('profile', 'claim_followup')",
            name="ck_interview_result_mode",
        ),
        CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'revoked')",
            name="ck_interview_result_status",
        ),
        Index(
            "ix_interview_result_user_status",
            "user_id",
            "status",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fair_use_session_id = Column(
        String(36),
        ForeignKey("interview_usage_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_id = Column(
        String(36),
        ForeignKey("resumes.id", ondelete="SET NULL"),
        nullable=True,
    )
    application_id = Column(
        String(36),
        ForeignKey("job_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode = Column(String(24), nullable=False)
    status = Column(
        String(24),
        nullable=False,
        default="pending_confirmation",
    )
    transcript = Column(JSON, nullable=False, default=list)
    extracted_json = Column(JSON, nullable=False, default=dict)
    source_references = Column(JSON, nullable=False, default=list)
    requested_uses = Column(JSON, nullable=False, default=dict)
    allowed_uses = Column(JSON, nullable=False, default=dict)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User")
    resume = relationship("Resume")
    application = relationship("JobApplication")


class UsageEvent(Base):
    """用户/企业功能用量；供应商成本只记录在 ProviderCostEvent。"""

    __tablename__ = "usage_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    billing_account_type = Column(String(20), nullable=True, default="user")
    billing_account_id = Column(
        String(36),
        nullable=True,
        default=_default_user_billing_account,
    )
    feature = Column(String(64), nullable=False)
    units = Column(Integer, default=1)
    month_key = Column(String(7), nullable=False)  # YYYY-MM
    period_key = Column(
        String(32),
        nullable=True,
        default=_default_usage_period,
    )
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class UsageReservation(Base):
    """PR5 原子配额预占；成功用量仍写入 UsageEvent 兼容旧汇总。"""

    __tablename__ = "usage_reservations"
    __table_args__ = (
        UniqueConstraint(
            "billing_account_type",
            "billing_account_id",
            "feature",
            "period_key",
            "idempotency_key",
            "attempt",
            name="uq_usage_reservation_account_attempt",
        ),
        CheckConstraint(
            "status IN ('reserved', 'succeeded', 'released')",
            name="ck_usage_reservation_status",
        ),
        Index(
            "ix_usage_reservation_quota",
            "billing_account_type",
            "billing_account_id",
            "feature",
            "period_key",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    billing_account_type = Column(String(20), nullable=True, default="user")
    billing_account_id = Column(String(36), nullable=True)
    feature = Column(String(64), nullable=False)
    month_key = Column(String(7), nullable=False)
    period_key = Column(String(32), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(64), nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    reserved_units = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="reserved")
    error_code = Column(String(64), nullable=True)
    model_called = Column(Boolean, nullable=False, default=False)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User")


class ProviderCostEvent(Base):
    """真实模型调用的供应商 token 与成本账，仅管理员接口可读取。"""

    __tablename__ = "provider_cost_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_request_id",
            name="uq_provider_cost_request",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND cache_hit_tokens >= 0 AND cache_miss_tokens >= 0",
            name="ck_provider_cost_nonnegative_tokens",
        ),
        CheckConstraint(
            "cost_microunits >= 0 AND cost_minor_units >= 0",
            name="ck_provider_cost_nonnegative_amount",
        ),
        CheckConstraint(
            "provider_status IN ('succeeded', 'failed', 'canceled', 'unknown')",
            name="ck_provider_cost_status",
        ),
        Index(
            "ix_provider_cost_created_feature",
            "created_at",
            "feature",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reservation_id = Column(
        String(36),
        ForeignKey("usage_reservations.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    feature = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    provider_request_id = Column(String(255), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_hit_tokens = Column(Integer, nullable=False, default=0)
    cache_miss_tokens = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False)
    # 精确账使用每货币单位的百万分之一；minor_units 是面向财务汇总的分。
    cost_microunits = Column(Integer, nullable=False, default=0)
    cost_minor_units = Column(Integer, nullable=False, default=0)
    price_version = Column(String(64), nullable=False)
    provider_status = Column(String(20), nullable=False, default="unknown")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reservation = relationship("UsageReservation")
    user = relationship("User")
    organization = relationship("Organization")


class CredibilityAuditRecord(Base):
    """可信度审计历史（用于再审计对比与训练数据飞轮）。"""

    __tablename__ = "credibility_audit_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=True)
    overall_status = Column(String(32), nullable=True)
    risk_score = Column(Float, nullable=True)
    report = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employer = relationship("User")
    job = relationship("JobDescription")
    resume = relationship("Resume")
    application = relationship("JobApplication")


class AuditFindingFeedback(Base):
    """雇主对审计 finding 的有用/误报反馈，供后续小模型训练。"""

    __tablename__ = "audit_finding_feedback"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_record_id = Column(String(36), ForeignKey("credibility_audit_records.id"), nullable=True)
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=True)
    claim_id = Column(String(128), nullable=True)
    finding_id = Column(String(128), nullable=True)
    finding_snapshot = Column(JSON, nullable=True)  # 脱敏后的 finding 摘要
    label = Column(String(32), nullable=False)  # useful | false_positive | unclear
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employer = relationship("User")
    audit_record = relationship("CredibilityAuditRecord")
    application = relationship("JobApplication")


class Company(Base):
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    name_aliases = Column(JSON, default=list)
    tier = Column(String(32), default="other")  # fortune500 / hot / other
    industry = Column(String(64), nullable=True)
    country = Column(String(32), default="CN")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    market_insights = relationship("MarketInsight", back_populates="company")
    hired_benchmarks = relationship("HiredProfileBenchmark", back_populates="company")


class MarketInsight(Base):
    """基于公开招聘 JD 聚合的岗位偏好"""

    __tablename__ = "market_insights"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    role_family = Column(String(64), default="general")
    jd_sample_size = Column(Integer, default=0)
    skill_freq = Column(JSON, default=dict)
    education_freq = Column(JSON, default=dict)
    school_tier_freq = Column(JSON, default=dict)
    soft_skill_freq = Column(JSON, default=dict)
    leadership_freq = Column(JSON, default=dict)
    communication_freq = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="market_insights")


class ForumInsightPost(Base):
    """网络招聘经验帖（原始）"""

    __tablename__ = "forum_insight_posts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform = Column(String(32), nullable=False)
    source_url = Column(Text, nullable=True)
    content_hash = Column(String(32), nullable=False, unique=True)
    title = Column(Text, nullable=True)
    body = Column(Text, nullable=False)
    search_query = Column(String(255), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    extractions = relationship("ForumInsightExtracted", back_populates="post")


class ForumInsightExtracted(Base):
    """从经验帖抽取的结构化信号"""

    __tablename__ = "forum_insight_extracted"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    post_id = Column(String(36), ForeignKey("forum_insight_posts.id"), nullable=False)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    company_name_raw = Column(String(255), nullable=True)
    role_family = Column(String(64), default="general")
    school_tier = Column(String(32), nullable=True)
    degree = Column(String(64), nullable=True)
    skills = Column(JSON, default=list)
    soft_skills = Column(JSON, default=list)
    leadership_signals = Column(JSON, default=list)
    platform = Column(String(32), nullable=True)
    extraction_confidence = Column(Float, default=0.5)
    weight = Column(Float, default=0.5)
    is_offer_story = Column(Integer, default=0)
    post_type = Column(String(20), default="discussion")
    recruitment_type = Column(String(20), default="unknown")

    post = relationship("ForumInsightPost", back_populates="extractions")
    company = relationship("Company")


class HiredProfileBenchmark(Base):
    """录用画像基准（统计模型为主）"""

    __tablename__ = "hired_profile_benchmarks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    role_family = Column(String(64), default="general")
    school_tier_dist = Column(JSON, default=dict)
    skill_freq = Column(JSON, default=dict)
    soft_skill_freq = Column(JSON, default=dict)
    leadership_freq = Column(JSON, default=dict)
    degree_freq = Column(JSON, default=dict)
    source = Column(String(32), default="statistical_forum")
    n_samples = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    source_breakdown = Column(JSON, default=dict)
    statistical_summary = Column(JSON, default=dict)
    methodology = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="hired_benchmarks")


class HiredProfileSubmission(Base):
    """用户自愿提交的录用画像（脱敏）"""

    __tablename__ = "hired_profile_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    role_title = Column(String(255), nullable=False)
    role_family = Column(String(64), default="general")
    school = Column(String(255), nullable=True)
    degree = Column(String(64), nullable=True)
    school_tier = Column(String(32), nullable=True)
    skills = Column(JSON, default=list)
    soft_skills = Column(JSON, default=list)
    leadership_examples = Column(JSON, default=list)
    hired_year = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")  # pending | approved | rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    company = relationship("Company")

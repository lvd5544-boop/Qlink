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
    Date,
    DateTime,
    BigInteger,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
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


class ResumeClaim(Base):
    """Stable, user-owned Passport claim; never a real-world verification verdict."""

    __tablename__ = "resume_claims"
    __table_args__ = (
        UniqueConstraint("resume_id", "source_key", name="uq_resume_claim_source_key"),
        CheckConstraint(
            "evidence_state IN ('supported_by_user_evidence', 'not_enough_information', 'conflict_detected')",
            name="ck_resume_claim_evidence_state",
        ),
        CheckConstraint(
            "workflow_state IN ('open', 'answered', 'reviewed', 'withdrawn')",
            name="ck_resume_claim_workflow_state",
        ),
        Index("ix_resume_claim_resume_state", "resume_id", "workflow_state", "updated_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    career_experience_id = Column(
        String(36), ForeignKey("career_experiences.id", ondelete="SET NULL"), nullable=True
    )
    origin_kind = Column(String(32), nullable=False, default="resume")
    source_object_type = Column(String(64), nullable=True)
    source_object_id = Column(String(36), nullable=True)
    source_span = Column(JSON, nullable=True)
    confirmation_state = Column(String(24), nullable=False, default="unconfirmed")
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    sensitivity_level = Column(String(24), nullable=False, default="normal")
    default_visibility = Column(String(32), nullable=False, default="private")
    superseded_by_claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="SET NULL"), nullable=True
    )
    # Compatibility key from claim_reasoning.  The UUID above is the Passport's stable ID.
    source_key = Column(String(160), nullable=False)
    section = Column(String(64), nullable=False)
    item_index = Column(Integer, nullable=True)
    field_path = Column(String(255), nullable=False)
    claim_type = Column(String(48), nullable=False)
    original_text = Column(Text, nullable=False)
    current_text = Column(Text, nullable=False)
    evidence_state = Column(String(48), nullable=False, default="not_enough_information")
    workflow_state = Column(String(24), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    resume = relationship("Resume", backref="passport_claims")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('user_statement', 'metric_context', 'document_reference', 'employer_review')",
            name="ck_claim_evidence_type",
        ),
        CheckConstraint(
            "verification_status IN ('user_provided', 'employer_reviewed', 'withdrawn')",
            name="ck_claim_evidence_verification_status",
        ),
        Index("ix_claim_evidence_claim_created", "claim_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type = Column(String(32), nullable=False)
    artifact_id = Column(
        String(36), ForeignKey("evidence_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    source_span = Column(JSON, nullable=True)
    link_created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    link_method = Column(String(24), nullable=False, default="manual")
    model_suggestion_id = Column(String(36), nullable=True)
    candidate_confirmed = Column(Boolean, nullable=False, default=True)
    access_scope = Column(String(32), nullable=False, default="private")
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    summary = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    provided_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verification_status = Column(String(32), nullable=False, default="user_provided")
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claim = relationship("ResumeClaim", backref="evidence")
    provider = relationship("User", foreign_keys=[provided_by])
    relationship = Column(String(24), nullable=False, default="supports")


class ClaimRevision(Base):
    __tablename__ = "claim_revisions"
    __table_args__ = (Index("ix_claim_revision_claim_created", "claim_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False
    )
    before_text = Column(Text, nullable=False)
    after_text = Column(Text, nullable=False)
    rewrite_mode = Column(String(48), nullable=True)
    evidence_ids = Column(JSON, nullable=True)
    model_version = Column(String(128), nullable=True)
    prompt_version = Column(String(128), nullable=True)
    rule_version = Column(String(128), nullable=True)
    fidelity_result = Column(JSON, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claim = relationship("ResumeClaim", backref="revisions")
    actor = relationship("User")


class ClaimApplicationLink(Base):
    __tablename__ = "claim_application_links"
    __table_args__ = (
        UniqueConstraint("claim_id", "application_id", name="uq_claim_application_link"),
        Index("ix_claim_application_link_application", "application_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="RESTRICT"), nullable=False
    )
    application_id = Column(
        String(36), ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False
    )
    text_snapshot = Column(Text, nullable=False)
    evidence_state_snapshot = Column(String(48), nullable=False)
    workflow_state_snapshot = Column(String(24), nullable=False)
    audit_snapshot = Column(JSON, nullable=True)
    employer_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claim = relationship("ResumeClaim", backref="application_links")
    application = relationship("JobApplication", backref="claim_passport_links")


class ClaimEvent(Base):
    """Append-only provenance event.  No API mutates or deletes this table."""

    __tablename__ = "claim_events"
    __table_args__ = (Index("ix_claim_event_claim_created", "claim_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="RESTRICT"), nullable=False
    )
    event_type = Column(String(64), nullable=False)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claim = relationship("ResumeClaim", backref="events")
    actor = relationship("User")


class PotentialSimulationEvent(Base):
    """Candidate-visible PR9 simulation audit trail; no employer ranking input."""

    __tablename__ = "potential_simulation_events"
    __table_args__ = (Index("ix_potential_simulation_resume_created", "resume_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    strategy_ids = Column(JSON, nullable=True)
    result_snapshot = Column(JSON, nullable=False)
    rule_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resume = relationship("Resume")
    job = relationship("JobDescription")
    user = relationship("User")


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
    structured_session_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship("User")
    resume = relationship("Resume")
    application = relationship("JobApplication")


class InterviewSession(Base):
    """PR12 structured interviewer session with explicit mode and consent snapshot."""

    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('vault_builder', 'target_gap', 'claim_clarification', 'practice')",
            name="ck_interview_session_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'revoked')",
            name="ck_interview_session_status",
        ),
        Index("ix_interview_sessions_user_status", "user_id", "status", "created_at"),
        Index("ix_interview_sessions_claim", "claim_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode = Column(String(32), nullable=False)
    job_id = Column(String(36), ForeignKey("job_descriptions.id", ondelete="SET NULL"), nullable=True)
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    claim_id = Column(String(36), ForeignKey("resume_claims.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), nullable=False, default="active")
    consent_snapshot = Column(JSON, nullable=False, default=dict)
    policy_version = Column(String(64), nullable=False, default="interview_policy_v1")
    rubric_version = Column(String(64), nullable=False, default="interview_rubric_v1")
    prompt_version = Column(String(64), nullable=False, default="interview_prompt_v1")
    model_version = Column(String(64), nullable=True)
    ai_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="uq_interview_question_seq"),
        CheckConstraint("core_or_probe IN ('core', 'probe')", name="ck_interview_question_core_or_probe"),
        Index("ix_interview_questions_session", "session_id", "sequence_no"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no = Column(Integer, nullable=False)
    question_goal = Column(String(64), nullable=False)
    claim_id = Column(String(36), ForeignKey("resume_claims.id", ondelete="SET NULL"), nullable=True)
    requirement_id = Column(String(128), nullable=True)
    competency_id = Column(String(128), nullable=True)
    core_or_probe = Column(String(16), nullable=False, default="core")
    question_text = Column(Text, nullable=False)
    policy_version = Column(String(64), nullable=False, default="interview_policy_v1")
    generated_by = Column(String(32), nullable=False, default="rules")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_interview_answer_question"),
        Index("ix_interview_answers_question", "question_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(
        String(36), ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False
    )
    raw_answer_ref = Column(String(255), nullable=True)
    answer_text_snapshot = Column(Text, nullable=False, default="")
    user_declined = Column(Boolean, nullable=False, default=False)
    decline_reason = Column(String(64), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    allowed_uses = Column(JSON, nullable=False, default=dict)
    share_with_employer = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InterviewObservation(Base):
    __tablename__ = "interview_observations"
    __table_args__ = (
        CheckConstraint(
            "observation_type IN ("
            "'situation', 'task', 'candidate_action', 'team_action', 'method', "
            "'result', 'metric', 'evidence', 'reflection', 'preference', 'constraint'"
            ")",
            name="ck_interview_observation_type",
        ),
        CheckConstraint(
            "candidate_confirmation_state IN ('pending', 'confirmed', 'rejected')",
            name="ck_interview_observation_confirm",
        ),
        Index(
            "ix_interview_observations_answer",
            "answer_id",
            "candidate_confirmation_state",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    answer_id = Column(
        String(36), ForeignKey("interview_answers.id", ondelete="CASCADE"), nullable=False
    )
    observation_type = Column(String(32), nullable=False)
    text = Column(Text, nullable=False)
    source_start = Column(Integer, nullable=False)
    source_end = Column(Integer, nullable=False)
    claim_id = Column(String(36), ForeignKey("resume_claims.id", ondelete="SET NULL"), nullable=True)
    candidate_confirmation_state = Column(String(32), nullable=False, default="pending")
    extractor_version = Column(String(64), nullable=False, default="rules_obs_v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptimizationIssue(Base):
    """PR13 persisted, target-job-specific resume diagnosis."""

    __tablename__ = "optimization_issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('blocker', 'high', 'medium', 'low')",
            name="ck_optimization_issue_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed', 'superseded')",
            name="ck_optimization_issue_status",
        ),
        Index("ix_optimization_issues_diagnostic", "diagnostic_id", "severity", "created_at"),
        Index("ix_optimization_issues_resume_job", "resume_id", "job_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    diagnostic_id = Column(String(36), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    resume_version_id = Column(
        String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    job_id = Column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False
    )
    profile_snapshot_id = Column(String(36), nullable=True)
    issue_key = Column(String(160), nullable=False)
    issue_type = Column(String(64), nullable=False)
    target_requirement_id = Column(String(160), nullable=True)
    diagnosis = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False)
    source_refs = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="open")
    rule_version = Column(String(64), nullable=False)
    model_version = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptimizationIssueClaimLink(Base):
    __tablename__ = "optimization_issue_claim_links"
    __table_args__ = (
        UniqueConstraint(
            "issue_id", "claim_id", "relation", name="uq_optimization_issue_claim_relation"
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_id = Column(
        String(36), ForeignKey("optimization_issues.id", ondelete="CASCADE"), nullable=False
    )
    claim_id = Column(
        String(36), ForeignKey("resume_claims.id", ondelete="RESTRICT"), nullable=False
    )
    relation = Column(String(24), nullable=False, default="related")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OptimizationStrategyOption(Base):
    __tablename__ = "optimization_strategy_options"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'selected', 'rejected', 'superseded')",
            name="ck_optimization_strategy_status",
        ),
        Index("ix_optimization_strategies_issue", "issue_id", "recommended"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_id = Column(
        String(36), ForeignKey("optimization_issues.id", ondelete="CASCADE"), nullable=False
    )
    strategy = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    why = Column(Text, nullable=False)
    requires_evidence = Column(Boolean, nullable=False, default=True)
    can_apply_now = Column(Boolean, nullable=False, default=False)
    next_action = Column(String(64), nullable=False)
    affected_dimensions = Column(JSON, nullable=False, default=list)
    time_horizon = Column(String(32), nullable=False)
    user_cost = Column(String(32), nullable=False)
    hallucination_risk = Column(String(16), nullable=False, default="low")
    recommended = Column(Boolean, nullable=False, default=False)
    eligibility_reason = Column(Text, nullable=False)
    counterfactual_snapshot = Column(JSON, nullable=False, default=dict)
    expression_delta = Column(Float, nullable=False, default=0)
    evidence_delta = Column(Float, nullable=False, default=0)
    capability_delta = Column(Float, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="available")
    rule_version = Column(String(64), nullable=False)
    scoring_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReadinessAction(Base):
    __tablename__ = "readiness_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', 'abandoned')",
            name="ck_readiness_action_status",
        ),
        Index("ix_readiness_actions_user_job", "user_id", "job_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False
    )
    issue_id = Column(
        String(36), ForeignKey("optimization_issues.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id = Column(
        String(36), ForeignKey("optimization_strategy_options.id", ondelete="CASCADE"), nullable=False
    )
    action_type = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="planned")
    completion_evidence_id = Column(
        String(36), ForeignKey("evidence_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    expected_time_horizon = Column(String(32), nullable=False)
    user_cost = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ResumePatchProposal(Base):
    __tablename__ = "resume_patch_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'needs_confirmation', 'ready', 'applied', 'rejected', 'expired')",
            name="ck_resume_patch_status",
        ),
        Index("ix_resume_patch_resume_job", "resume_id", "target_job_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    resume_version_id = Column(
        String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    target_job_id = Column(
        String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False
    )
    issue_id = Column(
        String(36), ForeignKey("optimization_issues.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id = Column(
        String(36), ForeignKey("optimization_strategy_options.id", ondelete="CASCADE"), nullable=False
    )
    field_path = Column(String(255), nullable=False)
    before_text = Column(Text, nullable=False)
    after_text = Column(Text, nullable=False)
    atomic_changes = Column(JSON, nullable=False, default=list)
    source_claim_ids = Column(JSON, nullable=False, default=list)
    source_evidence_ids = Column(JSON, nullable=False, default=list)
    source_answer_ids = Column(JSON, nullable=False, default=list)
    fidelity_result = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="draft")
    prompt_version = Column(String(64), nullable=True)
    model_version = Column(String(128), nullable=True)
    rule_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_resume_version_id = Column(
        String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )


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


class DataSource(Base):
    """Registered external/internal data source for profiles and training."""

    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'restricted', 'revoked')",
            name="ck_data_sources_status",
        ),
        CheckConstraint(
            "layer IN ('A', 'B', 'C', 'D', 'E')",
            name="ck_data_sources_layer",
        ),
        Index("ix_data_sources_status_layer", "status", "layer"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    owner_organization = Column(String(255), nullable=True)
    acquisition_method = Column(String(64), nullable=False, default="manual")
    license_name = Column(String(255), nullable=True)
    license_url = Column(Text, nullable=True)
    contract_ref = Column(Text, nullable=True)
    allowed_product_uses = Column(JSON, default=list)
    training_allowed = Column(Boolean, nullable=False, default=False)
    contains_personal_data = Column(Boolean, nullable=False, default=False)
    processing_region = Column(String(64), nullable=False, default="cn-beijing")
    attribution_text = Column(Text, nullable=True)
    deletion_contact = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending_review")
    layer = Column(String(8), nullable=False, default="E")
    # The production bootstrap creates the current ORM schema before replaying
    # historical SQL migrations.  PR10's immutable seed predates this PR14
    # column, so the database default is required for that insert to remain
    # valid on a clean database.
    scope = Column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions = relationship("DataSourceVersion", back_populates="source")


class DataSourceVersion(Base):
    __tablename__ = "data_source_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_validation', 'published', 'superseded', 'revoked')",
            name="ck_data_source_version_status",
        ),
        Index("ix_data_source_versions_source", "source_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(
        String(36),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_version = Column(String(128), nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=True)
    effective_at = Column(DateTime(timezone=True), nullable=True)
    checksum = Column(String(128), nullable=True)
    raw_object_ref = Column(Text, nullable=True)
    parser_version = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    validation_report = Column(JSON, nullable=True)
    superseded_by_version_id = Column(String(36), nullable=True)
    status = Column(String(32), nullable=False, default="pending_validation")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("DataSource", back_populates="versions")


class TargetRoleProfileSnapshot(Base):
    """Immutable PR14 four-layer target-role profile."""

    __tablename__ = "target_role_profile_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'employer_confirmed', 'superseded')",
            name="ck_target_role_profile_status",
        ),
        UniqueConstraint(
            "job_id",
            "snapshot_hash",
            name="uq_target_role_profile_job_hash",
        ),
        Index(
            "ix_target_role_profile_job_status",
            "job_id",
            "status",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(
        String(36),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    jd_snapshot_hash = Column(String(64), nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    profile_schema_version = Column(String(64), nullable=False)
    parser_version = Column(String(64), nullable=False)
    rule_version = Column(String(64), nullable=False)
    model_version = Column(String(128), nullable=True)
    taxonomy_version = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    occupation_profile = Column(JSON, nullable=False, default=dict)
    company_context_profile = Column(JSON, nullable=False, default=dict)
    market_signal_profile = Column(JSON, nullable=False, default=dict)
    source_manifest = Column(JSON, nullable=False, default=list)
    freshness_expires_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class JobRequirement(Base):
    """One employer-JD requirement attached to an immutable profile snapshot."""

    __tablename__ = "job_requirements"
    __table_args__ = (
        CheckConstraint(
            "requirement_type IN ("
            "'task','skill','experience','education','certificate','location',"
            "'salary','work_mode','other'"
            ")",
            name="ck_job_requirement_type",
        ),
        CheckConstraint(
            "requirement_level IN ('required','preferred','context')",
            name="ck_job_requirement_level",
        ),
        Index(
            "ix_job_requirements_snapshot",
            "profile_snapshot_id",
            "requirement_type",
            "importance",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_snapshot_id = Column(
        String(36),
        ForeignKey("target_role_profile_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_type = Column(String(32), nullable=False)
    raw_text = Column(Text, nullable=False)
    canonical_id = Column(String(160), nullable=True)
    canonical_label = Column(String(255), nullable=True)
    importance = Column(Integer, nullable=False, default=50)
    requirement_level = Column(String(24), nullable=False, default="required")
    is_hard_constraint = Column(Boolean, nullable=False, default=False)
    employer_confirmed = Column(Boolean, nullable=False, default=False)
    source_offset = Column(JSON, nullable=True)
    source_id = Column(String(128), nullable=True)
    source_version_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdvisorMessage(Base):
    """Persisted grounded advisor message and its user-visible response trace."""

    __tablename__ = "advisor_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','advisor')",
            name="ck_advisor_message_role",
        ),
        Index(
            "ix_advisor_messages_user_job",
            "user_id",
            "job_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id = Column(
        String(36),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_snapshot_id = Column(
        String(36),
        ForeignKey("target_role_profile_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    statements = Column(JSON, nullable=False, default=list)
    response_trace = Column(JSON, nullable=False, default=dict)
    prompt_version = Column(String(64), nullable=True)
    model_version = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIInvocation(Base):
    """Task-level AI invocation metadata; no raw resume/evidence bodies."""

    __tablename__ = "ai_invocations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'canceled', 'skipped', 'unknown')",
            name="ck_ai_invocations_status",
        ),
        Index("ix_ai_invocations_created_task", "created_at", "task_type"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    model_alias = Column(String(128), nullable=True)
    model_id = Column(String(128), nullable=False)
    prompt_version = Column(String(64), nullable=True)
    schema_version = Column(String(64), nullable=True)
    input_snapshot_hash = Column(String(128), nullable=False)
    data_region = Column(String(64), nullable=False, default="cn-beijing")
    token_input = Column(Integer, nullable=True)
    token_output = Column(Integer, nullable=True)
    cost_microunits = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False)
    error_category = Column(String(64), nullable=True)
    user_id = Column(String(36), nullable=True)
    org_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CareerExperience(Base):
    __tablename__ = "career_experiences"
    __table_args__ = (
        CheckConstraint(
            "experience_type IN ('work','project','education','volunteer','freelance','award','other')",
            name="ck_career_experience_type",
        ),
        CheckConstraint(
            "date_precision IN ('day','month','year','unknown')",
            name="ck_career_experience_precision",
        ),
        CheckConstraint(
            "workflow_state IN ('active','archived','withdrawn')",
            name="ck_career_experience_state",
        ),
        Index("ix_career_experiences_user_time", "user_id", "start_date", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    experience_type = Column(String(24), nullable=False)
    organization = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    date_precision = Column(String(16), nullable=False, default="unknown")
    description = Column(Text, nullable=True)
    source_kind = Column(String(32), nullable=False, default="manual")
    source_ref = Column(Text, nullable=True)
    workflow_state = Column(String(24), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('document','link','code','sample','certificate','image','user_statement','other')",
            name="ck_evidence_artifact_type",
        ),
        CheckConstraint(
            "verification_status IN ('user_provided','third_party_verified','rejected','withdrawn')",
            name="ck_evidence_artifact_verification",
        ),
        Index("ix_evidence_artifacts_owner_created", "owner_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    object_ref = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    mime_type = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    extracted_text_ref = Column(Text, nullable=True)
    issuer = Column(String(255), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(String(32), nullable=False, default="user_provided")
    verification_ref = Column(Text, nullable=True)
    allowed_uses = Column(JSON, nullable=False, default=list)
    default_visibility = Column(String(32), nullable=False, default="private")
    retention_until = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("resume_id", "version_number", name="uq_resume_version_number"),
        Index("ix_resume_versions_user_created", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    parsed_json_snapshot = Column(JSON, nullable=False)
    raw_text_snapshot = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=False)
    created_reason = Column(String(32), nullable=False)
    parent_version_id = Column(
        String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ResumeVersionClaimLink(Base):
    __tablename__ = "resume_version_claim_links"
    __table_args__ = (
        UniqueConstraint(
            "resume_version_id", "claim_id", "field_path",
            name="uq_resume_version_claim_field",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_version_id = Column(
        String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    claim_id = Column(String(36), ForeignKey("resume_claims.id", ondelete="RESTRICT"), nullable=False)
    claim_revision_id = Column(
        String(36), ForeignKey("claim_revisions.id", ondelete="SET NULL"), nullable=True
    )
    field_path = Column(String(255), nullable=False)
    text_snapshot = Column(Text, nullable=False)
    evidence_ids_snapshot = Column(JSON, nullable=False, default=list)
    fidelity_result_snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MigrationOrphanReport(Base):
    __tablename__ = "migration_orphan_reports"
    __table_args__ = (
        UniqueConstraint("migration_version", "entity_type", "entity_id", name="uq_migration_orphan"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    migration_version = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(36), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiIdempotencyKey(Base):
    """Replay ledger for PR11 Career Passport / Evidence Vault write APIs."""

    __tablename__ = "api_idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scope",
            "idempotency_key",
            name="uq_api_idempotency_user_scope_key",
        ),
        Index("ix_api_idempotency_expires", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope = Column(String(96), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)


class DecisionTrace(Base):
    """User-visible structured decision basis; never stores chain-of-thought."""

    __tablename__ = "decision_traces"
    __table_args__ = (
        Index(
            "ix_decision_traces_subject",
            "subject_type",
            "subject_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    decision_type = Column(String(64), nullable=False)
    subject_type = Column(String(64), nullable=False)
    subject_id = Column(String(36), nullable=False)
    observed_source_refs = Column(JSON, nullable=False, default=list)
    rules_fired = Column(JSON, nullable=False, default=list)
    findings = Column(JSON, nullable=False, default=list)
    alternative_explanations = Column(JSON, nullable=False, default=list)
    uncertainties = Column(JSON, nullable=False, default=list)
    recommended_next_actions = Column(JSON, nullable=False, default=list)
    human_review_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScreeningRun(Base):
    """Employer batch screening run pinned to an immutable profile snapshot."""

    __tablename__ = "screening_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'configured', 'running', 'completed', 'failed')",
            name="ck_screening_run_status",
        ),
        Index(
            "ix_screening_runs_employer_job",
            "employer_id",
            "job_id",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(
        String(36),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    employer_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_snapshot_id = Column(
        String(36),
        ForeignKey("target_role_profile_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profile_snapshot_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    candidate_count = Column(Integer, nullable=False, default=0)
    rules_version = Column(String(64), nullable=False, default="screening_rules_v1")
    keyword_version = Column(String(64), nullable=False, default="keyword_v1")
    model_version = Column(String(128), nullable=True)
    created_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ScreeningRule(Base):
    """Hard / keyword / taxonomy rule attached to a screening run."""

    __tablename__ = "screening_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('hard_constraint', 'keyword', 'taxonomy')",
            name="ck_screening_rule_type",
        ),
        Index("ix_screening_rules_run_order", "run_id", "order_no", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        String(36),
        ForeignKey("screening_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_type = Column(String(32), nullable=False)
    field = Column(String(64), nullable=False)
    operator = Column(String(32), nullable=False)
    value = Column(JSON, nullable=False, default=dict)
    job_requirement_id = Column(
        String(36),
        ForeignKey("job_requirements.id", ondelete="RESTRICT"),
        nullable=True,
    )
    employer_confirmed = Column(Boolean, nullable=False, default=False)
    legal_basis_note = Column(Text, nullable=True)
    order_no = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScreeningResult(Base):
    """Per-application screening outcome; never auto-rejects the application."""

    __tablename__ = "screening_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "application_id",
            name="uq_screening_result_run_application",
        ),
        CheckConstraint(
            "hard_filter_status IN ('pass', 'fail', 'unknown')",
            name="ck_screening_hard_filter",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'reviewed', 'clarification_requested')",
            name="ck_screening_result_status",
        ),
        Index("ix_screening_results_run_status", "run_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        String(36),
        ForeignKey("screening_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id = Column(
        String(36),
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    hard_filter_status = Column(String(16), nullable=False)
    hard_filter_reasons = Column(JSON, nullable=False, default=list)
    keyword_hits = Column(JSON, nullable=False, default=list)
    evidence_summary = Column(JSON, nullable=False, default=list)
    gap_findings = Column(JSON, nullable=False, default=list)
    consistency_findings = Column(JSON, nullable=False, default=list)
    alternative_explanations = Column(JSON, nullable=False, default=list)
    suggested_followups = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="pending_review")
    resume_version_id = Column(String(128), nullable=True)
    resume_content_hash = Column(String(128), nullable=False)
    requirement_refs = Column(JSON, nullable=False, default=list)
    claim_refs = Column(JSON, nullable=False, default=list)
    decision_trace_id = Column(
        String(36),
        ForeignKey("decision_traces.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewer_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

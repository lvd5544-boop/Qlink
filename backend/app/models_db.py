# 修改导入部分，移除 Vector
from sqlalchemy import Column, Integer, String, Text, Float, JSON, DateTime, ForeignKey, func  # noqa: F401
from sqlalchemy.orm import relationship
from .database import Base
# from pgvector.sqlalchemy import Vector   # 暂时注释掉
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(128), nullable=True)   # 新增
    role = Column(String(20), default="candidate")        # 新增，默认求职者
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resumes = relationship("Resume", back_populates="user")

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
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=True)   # 简化：招聘方也是 user 表的一条记录
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=True)
    parsed_json = Column(JSON, nullable=False)   # 存储 AI 解析后的结构化岗位
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    employer = relationship("User", backref="job_descriptions")

class MatchResult(Base):
    __tablename__ = "match_results"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    score = Column(Float, nullable=False)        # LLM 评分 0-10
    reason = Column(Text, nullable=True)         # 匹配理由
    score_breakdown = Column(JSON, nullable=True)  # 分项得分明细
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resume = relationship("Resume", backref="match_results")
    job = relationship("JobDescription", backref="match_results")

class InterviewInvitation(Base):
    __tablename__ = "interview_invitations"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    candidate_id = Column(String(36), ForeignKey("users.id"), nullable=False)  # 求职者 user_id
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=True)   # 关联的简历
    status = Column(String(20), default="pending")  # pending / accepted / declined
    message = Column(Text, nullable=True)
    proposed_time = Column(String(255), nullable=True)  # 提议面试时间（如 "2026-05-10 14:00"）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("JobDescription")
    employer = relationship("User", foreign_keys=[employer_id])
    candidate = relationship("User", foreign_keys=[candidate_id])
    resume = relationship("Resume")

class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("job_descriptions.id"), nullable=False)
    employer_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    candidate_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    status = Column(String(20), default="submitted")
    cover_letter = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("JobDescription")
    employer = relationship("User", foreign_keys=[employer_id])
    candidate = relationship("User", foreign_keys=[candidate_id])
    resume = relationship("Resume")

class ApplicationMessage(Base):
    __tablename__ = "application_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=False)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("JobApplication", backref="messages")
    sender = relationship("User")


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

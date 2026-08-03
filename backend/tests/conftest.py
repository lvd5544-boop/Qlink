"""
PR0 测试基线：独立测试库、多角色 fixture、FastAPI 客户端与认证 helper。

隔离规则：
- 默认使用本地 sqlite 文件 backend/tests/.testdata/jobplatform_test.db
- 可通过 TEST_DATABASE_URL / DATABASE_URL 指向 PostgreSQL，库名须含 jobplatform_test
- 拒绝连接默认开发库 jobplatform（无 _test 后缀）
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 必须在导入 app.* 之前设置环境，避免 load_dotenv / 引擎绑定到开发库
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_TESTDATA = Path(__file__).resolve().parent / ".testdata"
_TESTDATA.mkdir(parents=True, exist_ok=True)
_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{(_TESTDATA / 'jobplatform_test.db').as_posix()}"

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ["TESTING"] = "1"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only!")
os.environ.setdefault("METERING_ENABLED", "false")
os.environ.setdefault("EVIDENCE_FOLLOWUP_STRICT", "true")
os.environ.setdefault("EVIDENCE_VAULT_DIR", str(_TESTDATA / "evidence_vault"))
os.environ.setdefault("OBJECT_STORAGE_BACKEND", "local")
os.environ.setdefault("VIRUS_SCAN_ENABLED", "true")
os.environ.setdefault("VIRUS_SCAN_FAIL_MODE", "open")

_raw_url = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or _DEFAULT_SQLITE
).strip()


def _assert_safe_test_database_url(url: str) -> str:
    lowered = url.lower()
    if "sqlite" in lowered:
        return url
    # Postgres：必须显式指向测试库
    if "jobplatform_test" in lowered:
        return url
    if os.environ.get("ALLOW_UNSAFE_TEST_DB", "").strip() == "1":
        return url
    raise RuntimeError(
        "拒绝在非测试数据库上运行 pytest。"
        "请设置 TEST_DATABASE_URL 指向库名含 jobplatform_test 的库，"
        f"或使用默认 sqlite。当前 URL 已脱敏拒绝。原始 scheme={url.split(':', 1)[0]}"
    )


TEST_DATABASE_URL = _assert_safe_test_database_url(_raw_url)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import create_access_token, get_password_hash
from app.application_state import capture_resume_snapshot
from app.claim_threads import open_claim_thread
from app.database import Base, engine as app_engine, get_db
from app.models_db import (
    ApplicationMessage,
    CredibilityAuditRecord,
    JobApplication,
    JobDescription,
    MatchResult,
    Resume,
    User,
)

# 在 DATABASE_URL 已指向测试库后再导入应用（与 app_engine 同一 URL）
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# 引擎 / 会话（复用 app.database.engine，避免双连接锁 SQLite）
# ---------------------------------------------------------------------------
_sqlite_schema_initialized = False
_postgres_schema_initialized = False


@pytest_asyncio.fixture
async def test_engine():
    global _sqlite_schema_initialized, _postgres_schema_initialized
    # function scope：兼容 pytest-asyncio 默认 function event loop，避免 session fixture 跨 loop
    async with app_engine.begin() as conn:
        if conn.dialect.name == "sqlite" and not _sqlite_schema_initialized:
            # SQLite 测试库是可丢弃资产且不执行 PostgreSQL migration。
            # 每次 pytest 进程首次启动时按当前 metadata 重建，避免旧测试
            # 文件的残留列制造假失败；用例之间仍由 clean_tables 清数据。
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql" and not _postgres_schema_initialized:
            # 已存在的隔离 PG 测试库需要通过正式 migration 升到当前 metadata；
            # create_all 不会为旧表补列。
            migration = (
                _BACKEND_ROOT / "scripts" / "migrations" / "20260725_pr5_1_metering_accounts_up.sql"
            ).read_text(encoding="utf-8")
            interview_results_migration = (
                _BACKEND_ROOT / "scripts" / "migrations" / "20260725_pr5_1_interview_results_up.sql"
            ).read_text(encoding="utf-8")
            for sql_text in (migration, interview_results_migration):
                for statement in (part.strip() for part in sql_text.split(";")):
                    if statement:
                        await conn.exec_driver_sql(statement)
            _postgres_schema_initialized = True
        if conn.dialect.name == "sqlite":
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            _sqlite_schema_initialized = True
    try:
        yield app_engine
    finally:
        # asyncpg connections are bound to the event loop that created them.
        # Dispose only for PostgreSQL so function-scoped loops never reuse a
        # pooled connection from a closed loop. Keep the SQLite file engine
        # intact so cleanup deletes remain visible to the next test.
        if app_engine.dialect.name == "postgresql":
            await app_engine.dispose()


async def _clear_all_tables(test_engine) -> None:
    """清空已通过测试库安全检查的数据库，兼容上次测试异常中断。"""
    async with test_engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            return

        if conn.dialect.name == "postgresql":
            # Several production tables intentionally form FK cycles. Deleting
            # metadata tables one by one is therefore order-dependent and can
            # leave rows behind after an interrupted run. This URL has already
            # passed the test-database guard above, so reset the isolated schema
            # atomically and let PostgreSQL follow every FK edge.
            preparer = conn.dialect.identifier_preparer
            table_names = ", ".join(
                preparer.quote(table.name) for table in Base.metadata.tables.values()
            )
            if table_names:
                await conn.exec_driver_sql(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
            return

        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(test_engine):
    """每个用例前后清空业务表，保证隔离且不触碰开发库。"""
    await _clear_all_tables(test_engine)
    try:
        yield
    finally:
        await _clear_all_tables(test_engine)


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 认证 helper
# ---------------------------------------------------------------------------
def auth_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_header():
    return auth_headers


# ---------------------------------------------------------------------------
# 用户 / 资源 fixtures
# ---------------------------------------------------------------------------
async def _make_user(
    db: AsyncSession, *, email: str, role: str, password: str = "test-pass-123"
) -> User:
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _sample_resume_json(name: str, title: str) -> dict:
    return {
        "name": name,
        "email": f"{name.lower().replace(' ', '')}@example.com",
        "expected_job_title": title,
        "summary": f"{name} 的简介",
        "skills": [{"name": "Python"}, {"name": "SQL"}],
        "work_experience": [
            {
                "company": f"{name} Corp",
                "position": "工程师",
                "duration_years": 2,
                "description": "负责订单模块开发与性能优化",
            }
        ],
        "projects": [],
    }


def _sample_job_json(title: str) -> dict:
    return {
        "title": title,
        "required_skills": ["Python", "SQL"],
        "description": f"{title} 岗位描述",
        "location": "上海",
    }


@pytest_asyncio.fixture
async def candidate_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="candidate_a@test.local", role="candidate")


@pytest_asyncio.fixture
async def candidate_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="candidate_b@test.local", role="candidate")


@pytest_asyncio.fixture
async def employer_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="employer_a@test.local", role="employer")


@pytest_asyncio.fixture
async def employer_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="employer_b@test.local", role="employer")


@pytest_asyncio.fixture
async def billing_catalog(db_session: AsyncSession):
    from app.models_db import CreditPackProduct, Plan, PlanEntitlement

    free = Plan(
        code="candidate-free-v1",
        audience="candidate",
        name="Candidate Free",
        currency="CNY",
        price_minor_units=0,
        billing_period="month",
        version=1,
        active=True,
    )
    pro = Plan(
        code="candidate-pro-v1",
        audience="candidate",
        name="Candidate Pro",
        currency="CNY",
        price_minor_units=2000,
        billing_period="month",
        version=1,
        active=True,
    )
    organization = Plan(
        code="organization-seat-v1",
        audience="organization",
        name="企业席位",
        currency="CNY",
        price_minor_units=30000,
        billing_period="month",
        version=1,
        active=True,
    )
    db_session.add_all([free, pro, organization])
    await db_session.flush()
    entitlements = []
    for plan_code in ("candidate-free-v1", "candidate-pro-v1"):
        entitlements.extend(
            [
                PlanEntitlement(
                    plan_code=plan_code,
                    feature="resume_coach",
                    limit_units=50,
                    period="month",
                    meter_type="paid_credit",
                ),
                PlanEntitlement(
                    plan_code=plan_code,
                    feature="evidence_regenerate",
                    limit_units=50,
                    period="month",
                    meter_type="paid_credit",
                ),
                PlanEntitlement(
                    plan_code=plan_code,
                    feature="interview_session",
                    limit_units=50,
                    period="day",
                    meter_type="fair_use",
                ),
                PlanEntitlement(
                    plan_code=plan_code,
                    feature="interview_turn",
                    limit_units=50,
                    period="session",
                    meter_type="fair_use",
                ),
            ]
        )
    db_session.add_all(
        entitlements
        + [
            PlanEntitlement(
                plan_code="organization-seat-v1",
                feature="credibility_audit",
                limit_units=300,
                period="month",
                meter_type="paid_credit",
            ),
            CreditPackProduct(
                code="organization-audit-100-v1",
                audience="organization",
                name="企业审计 100 Credits",
                feature="credibility_audit",
                currency="CNY",
                price_minor_units=10000,
                grant_units=100,
                version=1,
                active=True,
            ),
        ]
    )
    await db_session.commit()
    return {
        "candidate_free": free,
        "candidate_pro": pro,
        "organization": organization,
    }


@pytest_asyncio.fixture
async def candidate_free_subscription(
    db_session: AsyncSession,
    candidate_a: User,
    billing_catalog,
):
    from app.models_db import UserSubscription

    now = datetime.now(timezone.utc)
    subscription = UserSubscription(
        user_id=str(candidate_a.id),
        plan_code="candidate-free-v1",
        status="active",
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        source="pilot",
    )
    db_session.add(subscription)
    await db_session.commit()
    return subscription


@pytest_asyncio.fixture
async def employer_organization_subscription(
    db_session: AsyncSession,
    employer_a: User,
    billing_catalog,
):
    from app.models_db import (
        Organization,
        OrganizationMembership,
        OrganizationSubscription,
    )

    organization = Organization(name="Employer A Billing Organization")
    db_session.add(organization)
    await db_session.flush()
    db_session.add_all(
        [
            OrganizationMembership(
                organization_id=str(organization.id),
                user_id=str(employer_a.id),
                role="owner",
                status="active",
            ),
        ]
    )
    now = datetime.now(timezone.utc)
    subscription = OrganizationSubscription(
        organization_id=str(organization.id),
        plan_code="organization-seat-v1",
        seat_quantity=1,
        status="active",
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        source="pilot",
    )
    db_session.add(subscription)
    await db_session.commit()
    return subscription


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, email="admin@test.local", role="admin")


@pytest_asyncio.fixture
async def resume_a(db_session: AsyncSession, candidate_a: User) -> Resume:
    resume = Resume(
        user_id=str(candidate_a.id),
        raw_text="Candidate A resume",
        parsed_json=_sample_resume_json("Candidate A", "后端工程师"),
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)
    return resume


@pytest_asyncio.fixture
async def resume_b(db_session: AsyncSession, candidate_b: User) -> Resume:
    resume = Resume(
        user_id=str(candidate_b.id),
        raw_text="Candidate B resume",
        parsed_json=_sample_resume_json("Candidate B", "前端工程师"),
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)
    return resume


@pytest_asyncio.fixture
async def job_a(db_session: AsyncSession, employer_a: User) -> JobDescription:
    job = JobDescription(
        employer_id=str(employer_a.id),
        title="后端工程师 A",
        raw_text="Job A",
        parsed_json=_sample_job_json("后端工程师 A"),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest_asyncio.fixture
async def job_b(db_session: AsyncSession, employer_b: User) -> JobDescription:
    job = JobDescription(
        employer_id=str(employer_b.id),
        title="前端工程师 B",
        raw_text="Job B",
        parsed_json=_sample_job_json("前端工程师 B"),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest_asyncio.fixture
async def match_a(db_session: AsyncSession, resume_a: Resume, job_a: JobDescription) -> MatchResult:
    match = MatchResult(
        resume_id=str(resume_a.id),
        job_id=str(job_a.id),
        score=7.5,
        reason="fixture match",
        score_breakdown={"skills": 7},
    )
    db_session.add(match)
    await db_session.commit()
    await db_session.refresh(match)
    return match


@pytest_asyncio.fixture
async def application_a(
    db_session: AsyncSession,
    candidate_a: User,
    employer_a: User,
    resume_a: Resume,
    job_a: JobDescription,
) -> JobApplication:
    app_row = JobApplication(
        job_id=str(job_a.id),
        employer_id=str(employer_a.id),
        candidate_id=str(candidate_a.id),
        resume_id=str(resume_a.id),
        status="needs_clarification",
        cover_letter="fixture apply",
        pipeline_meta={},
    )
    capture_resume_snapshot(app_row, resume_a, actor_id=str(candidate_a.id))
    db_session.add(app_row)
    await db_session.flush()
    open_claim_thread(
        app_row,
        claim_id="work_experience_0_action_0",
        claim_text="负责订单模块开发与性能优化",
        request_message_id="msg-req-fixture-1",
        questions=["请补充可验证的性能指标？"],
    )
    open_claim_thread(
        app_row,
        claim_id="work_experience_0_action_1",
        claim_text="负责订单模块开发与性能优化",
        request_message_id="msg-req-fixture-2",
        questions=["该优化覆盖哪些接口？"],
    )
    await db_session.commit()
    await db_session.refresh(app_row)
    return app_row


@pytest_asyncio.fixture
async def application_b(
    db_session: AsyncSession,
    candidate_b: User,
    employer_b: User,
    resume_b: Resume,
    job_b: JobDescription,
) -> JobApplication:
    app_row = JobApplication(
        job_id=str(job_b.id),
        employer_id=str(employer_b.id),
        candidate_id=str(candidate_b.id),
        resume_id=str(resume_b.id),
        status="submitted",
        cover_letter="fixture apply b",
        pipeline_meta={},
    )
    capture_resume_snapshot(app_row, resume_b, actor_id=str(candidate_b.id))
    db_session.add(app_row)
    await db_session.commit()
    await db_session.refresh(app_row)
    return app_row


@pytest_asyncio.fixture
async def message_a(
    db_session: AsyncSession,
    application_a: JobApplication,
    employer_a: User,
) -> ApplicationMessage:
    msg = ApplicationMessage(
        application_id=str(application_a.id),
        sender_id=str(employer_a.id),
        body="[澄清请求]\n关于 claim：「负责订单模块开发与性能优化」\n请补充说明：请补充可验证的性能指标？",
        message_kind="clarification_request",
        message_meta={
            "claim_id": "work_experience_0_action_0",
            "claim_text": "负责订单模块开发与性能优化",
            "questions": ["请补充可验证的性能指标？"],
        },
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def audit_record_a(
    db_session: AsyncSession,
    employer_a: User,
    job_a: JobDescription,
    resume_a: Resume,
    application_a: JobApplication,
) -> CredibilityAuditRecord:
    record = CredibilityAuditRecord(
        employer_id=str(employer_a.id),
        job_id=str(job_a.id),
        resume_id=str(resume_a.id),
        application_id=str(application_a.id),
        overall_status="needs_clarification",
        risk_score=42.0,
        report={
            "overall_status": "needs_clarification",
            "findings": [
                {
                    "id": "finding_a_1",
                    "claim_id": "work_experience_0_action_0",
                    "severity": "medium",
                    "title": "缺少可验证指标",
                }
            ],
        },
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest_asyncio.fixture
async def audit_record_b(
    db_session: AsyncSession,
    employer_b: User,
    job_b: JobDescription,
    resume_b: Resume,
    application_b: JobApplication,
) -> CredibilityAuditRecord:
    record = CredibilityAuditRecord(
        employer_id=str(employer_b.id),
        job_id=str(job_b.id),
        resume_id=str(resume_b.id),
        application_id=str(application_b.id),
        overall_status="pass",
        risk_score=10.0,
        report={"overall_status": "pass", "findings": []},
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest_asyncio.fixture
async def tenant_graph(
    candidate_a,
    candidate_b,
    employer_a,
    employer_b,
    admin_user,
    resume_a,
    resume_b,
    job_a,
    job_b,
    match_a,
    application_a,
    application_b,
    message_a,
    audit_record_a,
    audit_record_b,
):
    """一站式租户图，供跨租户用例使用。"""
    return {
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
        "employer_a": employer_a,
        "employer_b": employer_b,
        "admin": admin_user,
        "resume_a": resume_a,
        "resume_b": resume_b,
        "job_a": job_a,
        "job_b": job_b,
        "match_a": match_a,
        "application_a": application_a,
        "application_b": application_b,
        "message_a": message_a,
        "audit_record_a": audit_record_a,
        "audit_record_b": audit_record_b,
    }

"""PR14 grounded four-layer target-role profiles and job advisor."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .ai.data_sources import assert_source_version_usable
from .models_db import (
    AdvisorMessage,
    DataSource,
    DataSourceVersion,
    JobDescription,
    JobRequirement,
    Resume,
    TargetRoleProfileSnapshot,
)

PROFILE_SCHEMA_VERSION = "target_role_profile_v1"
PROFILE_PARSER_VERSION = "jd_requirements_rules_v1"
PROFILE_RULE_VERSION = "four_layer_governance_v1"
TAXONOMY_VERSION = "cn-occupation-2022-crosswalk-v3"
ADVISOR_PROMPT_VERSION = "grounded_advisor_v1"

_TAXONOMY_SOURCE_ID = "pr14-cn-taxonomy"
_DEFAULT_FRESHNESS_DAYS = 30

_SKILL_ALIASES = {
    "python": ("Python", "软件和信息技术服务人员"),
    "java": ("Java", "软件和信息技术服务人员"),
    "javascript": ("JavaScript", "软件和信息技术服务人员"),
    "typescript": ("TypeScript", "软件和信息技术服务人员"),
    "sql": ("SQL", "软件和信息技术服务人员"),
    "postgresql": ("PostgreSQL", "软件和信息技术服务人员"),
    "redis": ("Redis", "软件和信息技术服务人员"),
    "docker": ("Docker", "软件和信息技术服务人员"),
    "kubernetes": ("Kubernetes", "软件和信息技术服务人员"),
    "机器学习": ("机器学习", "人工智能工程技术人员"),
    "人工智能": ("人工智能", "人工智能工程技术人员"),
    "数据分析": ("数据分析", "大数据工程技术人员"),
    "data labeling": ("数据标注与质量检查", "人工智能训练师"),
    "data annotation": ("数据标注与质量检查", "人工智能训练师"),
    "产品": ("产品设计与协作", "管理（工业）工程技术人员"),
    "销售": ("客户开发与销售", "营销员"),
}
_TITLE_OCCUPATIONS = {
    "software": "软件和信息技术服务人员",
    "developer": "软件和信息技术服务人员",
    "engineer": "软件和信息技术服务人员",
    "工程师": "软件和信息技术服务人员",
    "data scientist": "人工智能工程技术人员",
    "machine learning": "人工智能工程技术人员",
    "算法": "人工智能工程技术人员",
    "数据": "大数据工程技术人员",
    "analyst": "大数据工程技术人员",
    "labeling": "人工智能训练师",
    "annotation": "人工智能训练师",
    "product": "管理（工业）工程技术人员",
    "产品": "管理（工业）工程技术人员",
    "designer": "数字媒体艺术专业人员",
    "设计": "数字媒体艺术专业人员",
    "sales": "营销员",
    "marketing": "营销员",
    "销售": "营销员",
    "市场": "营销员",
}
_OCCUPATION_THEMES = {
    "软件和信息技术服务人员": ["需求理解与软件设计", "编码、测试与维护", "协作交付与质量保障"],
    "人工智能工程技术人员": ["数据与特征处理", "模型开发与评估", "部署监控与负责任应用"],
    "大数据工程技术人员": ["数据采集与治理", "分析建模与解释", "数据产品与业务协作"],
    "人工智能训练师": ["数据采集、清洗与标注", "标注质量检查与一致性复核", "问题反馈与流程改进"],
    "管理（工业）工程技术人员": ["需求与问题定义", "方案规划与跨团队协作", "效果评估与持续改进"],
    "数字媒体艺术专业人员": ["用户与场景理解", "视觉或交互方案设计", "原型验证与设计交付"],
    "营销员": ["市场与客户洞察", "方案沟通与渠道协作", "目标跟进与关系维护"],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _as_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("label") or "").strip()
    return str(value or "").strip()


def _unique_text(items: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _as_text(item)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def build_job_requirements(job: JobDescription) -> list[dict[str, Any]]:
    """Extract stable A-layer requirements without importing other profile layers."""
    parsed = job.parsed_json or {}
    rows: list[dict[str, Any]] = []

    def add(
        requirement_type: str,
        raw_text: Any,
        *,
        level: str = "required",
        importance: int = 70,
        hard: bool = False,
        canonical_label: str | None = None,
    ) -> None:
        text = _as_text(raw_text)
        if not text:
            return
        key = (requirement_type, text.casefold())
        if any((row["requirement_type"], row["raw_text"].casefold()) == key for row in rows):
            return
        canonical_slug = re.sub(
            r"[^a-z0-9\u4e00-\u9fff]+",
            "-",
            text.casefold(),
        ).strip("-")[:120]
        rows.append(
            {
                "requirement_type": requirement_type,
                "raw_text": text,
                "canonical_id": f"{requirement_type}:{canonical_slug}",
                "canonical_label": (canonical_label or text)[:255],
                "importance": importance,
                "requirement_level": level,
                "is_hard_constraint": hard,
            }
        )

    for item in _unique_text(parsed.get("responsibilities") or []):
        add("task", item, importance=80)
    for item in _unique_text(parsed.get("required_skills") or []):
        # A JD mention is not automatically a knockout condition. The employer
        # must explicitly promote an item to a hard constraint at confirmation.
        add("skill", item, importance=90, hard=False)
    for item in _unique_text(parsed.get("soft_skills") or []):
        add("skill", item, level="preferred", importance=55)

    if parsed.get("experience_years") is not None:
        add(
            "experience",
            f"{parsed['experience_years']} 年相关经验",
            importance=85,
            hard=False,
        )
    add(
        "education",
        parsed.get("education_requirement") or parsed.get("education"),
        importance=65,
    )
    add("location", parsed.get("location"), level="context", importance=45)
    add("salary", parsed.get("salary_range"), level="context", importance=35)
    add("work_mode", parsed.get("work_mode"), level="context", importance=45)

    freeform = parsed.get("requirements")
    if freeform:
        for fragment in re.split(r"[\n；;]+", str(freeform)):
            add("other", fragment, importance=60)
    return rows


async def _ensure_taxonomy_source(db: AsyncSession) -> tuple[DataSource, DataSourceVersion]:
    source = await db.get(DataSource, _TAXONOMY_SOURCE_ID)
    if source is None:
        source = DataSource(
            id=_TAXONOMY_SOURCE_ID,
            name="中国职业分类固定术语索引",
            owner_organization="QLink（依据《中华人民共和国职业分类大典（2022年版）》整理）",
            acquisition_method="curated_fixed_crosswalk",
            license_name="政府公开职业分类参考",
            license_url="https://www.mohrss.gov.cn/",
            allowed_product_uses=["formal_profile", "occupation_reference"],
            training_allowed=False,
            contains_personal_data=False,
            processing_region="cn-beijing",
            attribution_text="职业名称参考《中华人民共和国职业分类大典（2022年版）》",
            status="approved",
            layer="B",
            scope={"country": "CN", "profile_type": "occupation"},
        )
        db.add(source)
        await db.flush()
    version = (
        await db.execute(
            select(DataSourceVersion)
            .where(
                DataSourceVersion.source_id == source.id,
                DataSourceVersion.external_version == TAXONOMY_VERSION,
            )
            .order_by(DataSourceVersion.created_at.desc())
        )
    ).scalars().first()
    if version is None:
        version = DataSourceVersion(
            id=str(uuid.uuid4()),
            source_id=str(source.id),
            external_version=TAXONOMY_VERSION,
            retrieved_at=_utcnow(),
            effective_at=_utcnow(),
            checksum=_stable_hash(_SKILL_ALIASES),
            parser_version="curated_crosswalk_v1",
            status="published",
            validation_report={
                "method": "fixed curated term crosswalk",
                "does_not_override_employer_jd": True,
            },
        )
        db.add(version)
        await db.flush()
    return source, version


def _source_dict(source: DataSource) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "status": source.status,
        "layer": source.layer,
        "allowed_product_uses": source.allowed_product_uses or [],
    }


def _version_dict(version: DataSourceVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "status": version.status,
        "expires_at": version.expires_at,
        "superseded_by_version_id": version.superseded_by_version_id,
    }


def _scope_matches(source: DataSource, job: JobDescription) -> bool:
    scope = source.scope or {}
    job_ids = {str(item) for item in scope.get("job_ids") or []}
    if job_ids and str(job.id) not in job_ids:
        return False
    company_names = {str(item).strip().casefold() for item in scope.get("company_names") or []}
    company = str((job.parsed_json or {}).get("company_name") or "").strip().casefold()
    return not company_names or (company and company in company_names)


async def _active_external_sources(
    db: AsyncSession,
    job: JobDescription,
) -> list[tuple[DataSource, DataSourceVersion]]:
    sources = (
        await db.execute(
            select(DataSource).where(
                DataSource.status == "approved",
                DataSource.layer.in_(("B", "C", "D")),
            )
        )
    ).scalars().all()
    rows: list[tuple[DataSource, DataSourceVersion]] = []
    for source in sources:
        if not _scope_matches(source, job):
            continue
        version = (
            await db.execute(
                select(DataSourceVersion)
                .where(DataSourceVersion.source_id == str(source.id))
                .order_by(DataSourceVersion.created_at.desc())
            )
        ).scalars().first()
        if version is None:
            continue
        try:
            assert_source_version_usable(
                _source_dict(source),
                _version_dict(version),
            )
        except PermissionError:
            continue
        rows.append((source, version))
    return rows


def _citation(
    *,
    source_id: str,
    source_version_id: str,
    source_name: str,
    source_type: str,
    effective_at: datetime | None,
    scope: str,
    attribution: str | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_version_id": source_version_id,
        "source_name": source_name,
        "source_type": source_type,
        "effective_at": effective_at.isoformat() if effective_at else None,
        "scope": scope,
        "attribution": attribution,
    }


def _occupation_profile(
    job: JobDescription,
    source: DataSource,
    version: DataSourceVersion,
) -> dict[str, Any]:
    haystack = json.dumps(
        {"title": job.title, "parsed": job.parsed_json or {}},
        ensure_ascii=False,
    ).casefold()
    skills: list[str] = []
    occupations: list[str] = []
    for keyword, (skill, occupation) in _SKILL_ALIASES.items():
        if keyword.casefold() in haystack:
            if skill not in skills:
                skills.append(skill)
            if occupation not in occupations:
                occupations.append(occupation)
    for keyword, occupation in _TITLE_OCCUPATIONS.items():
        if keyword.casefold() in haystack and occupation not in occupations:
            occupations.append(occupation)
    work_themes = _unique_text(
        theme
        for occupation in occupations
        for theme in _OCCUPATION_THEMES.get(occupation, [])
    )
    citation = _citation(
        source_id=str(source.id),
        source_version_id=str(version.id),
        source_name=source.name,
        source_type="occupation_reference",
        effective_at=version.effective_at,
        scope="职业通用参考，不覆盖企业 JD",
        attribution=source.attribution_text,
    )
    return {
        "title": "该职业通常需要什么",
        "occupations": occupations,
        "adjacent_skills": skills,
        "work_themes": work_themes,
        "caveat": "职业通用参考仅用于技能归一化和成长路径，不能覆盖企业明确要求。",
        "citations": [citation],
        "empty_reason": (
            None
            if occupations
            else "岗位标题与 JD 暂未命中已发布的职业术语映射；不会用猜测强行归类。"
        ),
    }


def _external_layer_profile(
    layer: str,
    rows: list[tuple[DataSource, DataSourceVersion]],
) -> dict[str, Any]:
    matching = [(source, version) for source, version in rows if source.layer == layer]
    if layer == "C":
        title = "公司公开业务和工作语境是什么"
        caveat = "公开材料只说明业务语境，不代表该公司偏好某类候选人。"
        source_type = "company_context"
    else:
        title = "市场中出现了什么趋势"
        caveat = "市场聚合信号不代表具体企业，也不作为硬性岗位要求。"
        source_type = "market_signal"
    facts: list[str] = []
    citations: list[dict[str, Any]] = []
    for source, version in matching:
        report = version.validation_report or {}
        facts.extend(_unique_text(report.get("facts") or report.get("signals") or []))
        citations.append(
            _citation(
                source_id=str(source.id),
                source_version_id=str(version.id),
                source_name=source.name,
                source_type=source_type,
                effective_at=version.effective_at,
                scope=(
                    "公司公开业务语境，不得推断招聘偏好"
                    if layer == "C"
                    else "经许可、聚合后的市场趋势"
                ),
                attribution=source.attribution_text,
            )
        )
    return {
        "title": title,
        "facts": facts,
        "caveat": caveat,
        "citations": citations,
        "empty_reason": None if matching else "当前没有通过许可与版本审核的可用来源。",
        "source_status": {
            "approved_sources": len(matching),
            "required_layer": layer,
            "state": "ready" if matching else "awaiting_approved_source",
        },
        "next_step": (
            None
            if matching
            else (
                "需登记公司官网、年报或官方技术资料并通过版本审核。"
                if layer == "C"
                else "需接入取得许可、去标识化且完成版本审核的聚合岗位数据。"
            )
        ),
    }


async def get_or_create_profile(
    db: AsyncSession,
    job: JobDescription,
    *,
    actor_id: str | None,
) -> TargetRoleProfileSnapshot:
    taxonomy_source, taxonomy_version = await _ensure_taxonomy_source(db)
    external_sources = await _active_external_sources(db, job)
    if not any(source.id == taxonomy_source.id for source, _ in external_sources):
        external_sources.append((taxonomy_source, taxonomy_version))

    source_manifest = [
        {
            "source_id": str(source.id),
            "source_version_id": str(version.id),
            "layer": source.layer,
            "status": source.status,
            "version_status": version.status,
            "external_version": version.external_version,
            "checksum": version.checksum,
            "effective_at": _iso_utc(version.effective_at),
            "expires_at": _iso_utc(version.expires_at),
            "attribution": source.attribution_text,
        }
        for source, version in sorted(
            external_sources,
            key=lambda item: (item[0].layer, str(item[0].id), str(item[1].id)),
        )
    ]
    parsed_for_profile = {
        key: value
        for key, value in (job.parsed_json or {}).items()
        if not str(key).startswith("_")
    }
    jd_payload = {"title": job.title, "raw_text": job.raw_text, "parsed": parsed_for_profile}
    jd_hash = _stable_hash(jd_payload)
    snapshot_hash = _stable_hash(
        {
            "jd": jd_payload,
            "sources": source_manifest,
            "schema": PROFILE_SCHEMA_VERSION,
            "parser": PROFILE_PARSER_VERSION,
            "rules": PROFILE_RULE_VERSION,
            "taxonomy": TAXONOMY_VERSION,
        }
    )
    existing = (
        await db.execute(
            select(TargetRoleProfileSnapshot).where(
                TargetRoleProfileSnapshot.job_id == str(job.id),
                TargetRoleProfileSnapshot.snapshot_hash == snapshot_hash,
            )
        )
    ).scalars().first()
    if existing is not None:
        await db.commit()
        return existing

    previous = (
        await db.execute(
            select(TargetRoleProfileSnapshot).where(
                TargetRoleProfileSnapshot.job_id == str(job.id),
                TargetRoleProfileSnapshot.status.in_(("draft", "employer_confirmed")),
            )
        )
    ).scalars().all()
    for row in previous:
        row.status = "superseded"

    expiry_candidates = [
        version.expires_at
        for _, version in external_sources
        if version.expires_at is not None
    ]
    freshness = min(expiry_candidates) if expiry_candidates else _utcnow() + timedelta(
        days=_DEFAULT_FRESHNESS_DAYS
    )
    snapshot = TargetRoleProfileSnapshot(
        id=str(uuid.uuid4()),
        job_id=str(job.id),
        created_by=actor_id,
        jd_snapshot_hash=jd_hash,
        snapshot_hash=snapshot_hash,
        profile_schema_version=PROFILE_SCHEMA_VERSION,
        parser_version=PROFILE_PARSER_VERSION,
        rule_version=PROFILE_RULE_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        status="draft",
        occupation_profile=_occupation_profile(job, taxonomy_source, taxonomy_version),
        company_context_profile=_external_layer_profile("C", external_sources),
        market_signal_profile=_external_layer_profile("D", external_sources),
        source_manifest=source_manifest,
        freshness_expires_at=freshness,
    )
    db.add(snapshot)
    await db.flush()
    for requirement in build_job_requirements(job):
        db.add(
            JobRequirement(
                id=str(uuid.uuid4()),
                profile_snapshot_id=str(snapshot.id),
                **requirement,
                employer_confirmed=False,
                source_id=f"job:{job.id}",
                source_version_id=f"jd:{jd_hash[:24]}",
            )
        )
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def serialize_profile(
    db: AsyncSession,
    snapshot: TargetRoleProfileSnapshot,
    job: JobDescription,
) -> dict[str, Any]:
    requirements = (
        await db.execute(
            select(JobRequirement)
            .where(JobRequirement.profile_snapshot_id == str(snapshot.id))
            .order_by(JobRequirement.importance.desc(), JobRequirement.created_at)
        )
    ).scalars().all()
    jd_citation = _citation(
        source_id=f"job:{job.id}",
        source_version_id=f"jd:{snapshot.jd_snapshot_hash[:24]}",
        source_name=f"{job.title} · 企业 JD",
        source_type="employer_requirement",
        effective_at=job.created_at,
        scope="当前企业、当前岗位",
    )
    now = _utcnow()
    expires_at = snapshot.freshness_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "job": {
            "id": str(job.id),
            "title": job.title,
            "company_name": (job.parsed_json or {}).get("company_name"),
            "advisor_private": bool((job.parsed_json or {}).get("advisor_private")),
        },
        "snapshot": {
            "id": str(snapshot.id),
            "snapshot_hash": snapshot.snapshot_hash,
            "status": snapshot.status,
            "profile_schema_version": snapshot.profile_schema_version,
            "parser_version": snapshot.parser_version,
            "rule_version": snapshot.rule_version,
            "taxonomy_version": snapshot.taxonomy_version,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "freshness_expires_at": (
                snapshot.freshness_expires_at.isoformat()
                if snapshot.freshness_expires_at
                else None
            ),
            "is_stale": bool(expires_at and expires_at <= now),
        },
        "layers": {
            "target_role": {
                "title": "这个企业这个岗位明确要求什么",
                "requirements": [
                    {
                        "id": str(row.id),
                        "type": row.requirement_type,
                        "text": row.raw_text,
                        "canonical_label": row.canonical_label,
                        "importance": row.importance,
                        "level": row.requirement_level,
                        "is_hard_constraint": row.is_hard_constraint,
                        "employer_confirmed": row.employer_confirmed,
                        "citations": [jd_citation],
                    }
                    for row in requirements
                ],
                "citations": [jd_citation],
                "caveat": "只有企业 JD 或企业确认的内容才属于该企业岗位要求。",
            },
            "occupation": snapshot.occupation_profile or {},
            "company_context": snapshot.company_context_profile or {},
            "market_signal": snapshot.market_signal_profile or {},
        },
    }


async def confirm_profile(
    db: AsyncSession,
    snapshot: TargetRoleProfileSnapshot,
    *,
    employer_id: str,
    requirement_decisions: dict[str, str] | None = None,
) -> None:
    rows = (
        await db.execute(
            select(JobRequirement).where(
                JobRequirement.profile_snapshot_id == str(snapshot.id)
            )
        )
    ).scalars().all()
    if requirement_decisions is not None:
        row_ids = {str(row.id) for row in rows}
        if set(requirement_decisions) != row_ids:
            raise ValueError("requirement_decisions_incomplete")

    snapshot.status = "employer_confirmed"
    snapshot.confirmed_by = employer_id
    snapshot.confirmed_at = _utcnow()

    for row in rows:
        classification = (
            requirement_decisions.get(str(row.id))
            if requirement_decisions is not None
            else None
        )
        if classification == "hard":
            row.requirement_level = "required"
            row.is_hard_constraint = True
        elif classification == "preferred":
            row.requirement_level = "preferred"
            row.is_hard_constraint = False
        elif classification == "context":
            row.requirement_level = "context"
            row.is_hard_constraint = False
        elif classification is not None:
            raise ValueError("invalid_requirement_classification")
        row.employer_confirmed = True
    await db.flush()


def _resume_citation(resume: Resume) -> dict[str, Any]:
    return _citation(
        source_id=f"resume:{resume.id}",
        source_version_id=f"resume:{resume.id}:{_stable_hash(resume.parsed_json or {})[:16]}",
        source_name="你当前选择的简历",
        source_type="candidate_evidence",
        effective_at=resume.uploaded_at,
        scope="仅用于当前用户的岗位准备建议",
    )


async def answer_advisor(
    db: AsyncSession,
    *,
    user_id: str,
    job: JobDescription,
    snapshot: TargetRoleProfileSnapshot,
    message: str,
    resume: Resume | None,
) -> dict[str, Any]:
    profile = await serialize_profile(db, snapshot, job)
    user_message = AdvisorMessage(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_id=str(job.id),
        profile_snapshot_id=str(snapshot.id),
        role="user",
        content=message,
        statements=[],
        response_trace={},
    )
    db.add(user_message)

    target_requirements = profile["layers"]["target_role"]["requirements"]
    statements: list[dict[str, Any]] = []
    for requirement in target_requirements[:3]:
        statements.append(
            {
                "text": f"该岗位明确写到：{requirement['text']}",
                "statement_type": "employer_requirement",
                "confidence": "高：来自当前岗位 JD",
                "is_inference": False,
                "citations": requirement["citations"],
            }
        )

    candidate_skill_names: set[str] = set()
    resume_citation = None
    if resume is not None:
        candidate_skill_names = {
            _as_text(item).casefold()
            for item in (resume.parsed_json or {}).get("skills") or []
            if _as_text(item)
        }
        resume_citation = _resume_citation(resume)
        matched = [
            requirement["text"]
            for requirement in target_requirements
            if requirement["type"] == "skill"
            and requirement["text"].casefold() in candidate_skill_names
        ]
        if matched:
            statements.append(
                {
                    "text": f"你当前简历已经明确出现：{'、'.join(matched[:4])}。",
                    "statement_type": "candidate_evidence",
                    "confidence": "高：简历中有直接文本",
                    "is_inference": False,
                    "citations": [resume_citation],
                }
            )

    missing = [
        requirement
        for requirement in target_requirements
        if requirement["type"] == "skill"
        and requirement["text"].casefold() not in candidate_skill_names
    ]
    if missing:
        citations = list(missing[0]["citations"])
        if resume_citation:
            citations.append(resume_citation)
        statements.append(
            {
                "text": (
                    f"当前材料未观察到“{missing[0]['text']}”。先确认你是否真实使用过；"
                    "如果没有，应作为学习与实践行动，而不是直接写入简历。"
                ),
                "statement_type": "inference",
                "confidence": "中：由 JD 与当前材料对照得出",
                "is_inference": True,
                "citations": citations,
            }
        )
    elif target_requirements:
        top = target_requirements[0]
        citations = list(top["citations"])
        if resume_citation:
            citations.append(resume_citation)
        statements.append(
            {
                "text": (
                    f"建议先围绕“{top['text']}”准备一个可核对的具体案例，"
                    "再检查角色、方法、结果和证据是否完整。"
                ),
                "statement_type": "inference",
                "confidence": "中：根据岗位要求的重要度与当前材料生成行动顺序",
                "is_inference": True,
                "citations": citations,
            }
        )

    for layer_name, statement_type in (
        ("company_context", "company_context"),
        ("market_signal", "market_signal"),
    ):
        layer = profile["layers"][layer_name]
        if layer.get("facts") and layer.get("citations"):
            statements.append(
                {
                    "text": str(layer["facts"][0]),
                    "statement_type": statement_type,
                    "confidence": "中：来自已审核的公开或聚合来源",
                    "is_inference": False,
                    "citations": layer["citations"],
                }
            )

    if not statements:
        statements.append(
            {
                "text": "当前岗位材料不足，建议先补充完整 JD，再生成准备建议。",
                "statement_type": "inference",
                "confidence": "低：当前信息不足",
                "is_inference": True,
                "citations": profile["layers"]["target_role"]["citations"],
            }
        )
    if any(not item.get("citations") for item in statements):
        raise ValueError("advisor factual statement missing citation")

    content = "\n".join(f"• {item['text']}" for item in statements)
    trace = {
        "profile_snapshot_id": str(snapshot.id),
        "snapshot_hash": snapshot.snapshot_hash,
        "observed_source_refs": sorted(
            {
                citation["source_version_id"]
                for item in statements
                for citation in item["citations"]
            }
        ),
        "rules_fired": [
            "four_layers_remain_separate",
            "candidate_missing_is_not_capability_absence",
            "future_action_does_not_raise_current_readiness",
        ],
        "uncertainties": (
            ["未选择简历，无法核对候选人已有材料。"] if resume is None else []
        ),
        "alternative_explanations": [
            "简历未出现某项技能，可能是未写出，也可能是尚未具备；需要用户澄清。"
        ],
        "recommended_next_actions": [
            "核对岗位明确要求",
            "确认已有证据",
            "把真实缺口转为学习或实践行动",
        ],
        "human_review_required": False,
    }
    advisor_message = AdvisorMessage(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_id=str(job.id),
        profile_snapshot_id=str(snapshot.id),
        role="advisor",
        content=content,
        statements=statements,
        response_trace=trace,
        prompt_version=ADVISOR_PROMPT_VERSION,
        model_version="grounded-rules-v1",
    )
    db.add(advisor_message)
    await db.commit()
    await db.refresh(advisor_message)
    return {
        "id": str(advisor_message.id),
        "role": "advisor",
        "content": content,
        "statements": statements,
        "response_trace": trace,
        "created_at": (
            advisor_message.created_at.isoformat()
            if advisor_message.created_at
            else None
        ),
    }

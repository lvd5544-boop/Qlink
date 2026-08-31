"""PR15 employer batch screening: hard → keyword/taxonomy → LLM summary → human review."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .advisor import get_or_create_profile
from .application_authz import application_has_candidate_authorization
from .ai import InvocationContext, gateway_run
from .application_state import _content_hash, get_resume_snapshot
from .claim_passport import application_claim_snapshot_summary
from .interview_policy import is_sensitive_question
from .models_db import (
    DecisionTrace,
    JobApplication,
    JobDescription,
    JobRequirement,
    ScreeningResult,
    ScreeningRule,
    ScreeningRun,
    TargetRoleProfileSnapshot,
)

logger = logging.getLogger(__name__)

RULES_VERSION = "screening_rules_v1"
KEYWORD_VERSION = "keyword_v1"
SCREENING_PROMPT_VERSION = "screening_v1"

HARD_FIELDS = frozenset(
    {
        "years_experience",
        "education_level",
        "required_skill",
        "certificate",
        "location",
        "work_authorization",
    }
)
HARD_OPERATORS: dict[str, frozenset[str]] = {
    "years_experience": frozenset({"gte", "lte", "eq"}),
    "education_level": frozenset({"eq", "contains", "in"}),
    "required_skill": frozenset({"contains", "eq", "in"}),
    "certificate": frozenset({"contains", "eq", "in"}),
    "location": frozenset({"eq", "contains", "in"}),
    "work_authorization": frozenset({"eq", "in"}),
}
KEYWORD_FIELDS = frozenset({"keyword", "skill_keyword", "title_keyword"})
KEYWORD_OPERATORS = frozenset({"contains", "eq", "in"})
TAXONOMY_FIELDS = frozenset({"canonical_skill", "occupation"})
TAXONOMY_OPERATORS = frozenset({"eq", "in", "contains"})

_REQUIREMENT_TYPE_TO_FIELD = {
    "experience": "years_experience",
    "education": "education_level",
    "skill": "required_skill",
    "location": "location",
    "certificate": "certificate",
}

_SKILL_ALIASES = {
    "python": ("python", "py"),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "postgresql": ("postgresql", "postgres", "psql"),
    "kubernetes": ("kubernetes", "k8s"),
}

_SENSITIVE_RULE_PATTERN = re.compile(
    r"(?:户口|年龄|出生|婚姻|婚育|怀孕|性别|民族|种族|宗教|残疾|病史|健康状况)"
    r"|\b(?:age|birth|gender|sex|marital|pregnan(?:t|cy)?|ethnicity|race|"
    r"religion|disability|medical|health|hukou|household\s+registration)\b",
    re.IGNORECASE,
)

_PROHIBITED_PROXY_RULE_PATTERN = re.compile(
    r"(?:985|211|双一流|名校|院校层级|学校层级|院校排名|学校排名|绩点)"
    r"|\b(?:gpa|grade\s+point\s+average|school\s+(?:tier|prestige|ranking)|"
    r"university\s+(?:tier|prestige|ranking)|elite\s+(?:school|university))\b",
    re.IGNORECASE,
)


ScreeningText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=600),
]


class ScreeningLLMOutput(BaseModel):
    """Strict schema: assistive text only; never hard-filter or application status."""

    model_config = ConfigDict(extra="forbid")

    evidence_summary: list[ScreeningText] = Field(default_factory=list, max_length=8)
    alternative_explanations: list[ScreeningText] = Field(default_factory=list, max_length=8)
    suggested_followups: list[ScreeningText] = Field(default_factory=list, max_length=8)
    gap_findings: list[ScreeningText] = Field(default_factory=list, max_length=8)
    consistency_findings: list[ScreeningText] = Field(default_factory=list, max_length=8)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _not_found_error() -> ValueError:
    return ValueError("not_found")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_blob(parsed: dict | None) -> str:
    """Build searchable text from values, excluding schema field names.

    JSON keys such as ``skills`` or ``education`` are implementation details and
    must not count as evidence that a candidate supplied those terms.
    """
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                collect(nested)
        elif value is not None:
            text = str(value).strip()
            if text:
                values.append(text)

    collect(parsed or {})
    return "\n".join(values).casefold()


def _term_in_blob(blob: str, term: str) -> bool:
    """Match Latin technical terms on boundaries, not arbitrary substrings."""
    normalized = str(term or "").strip().casefold()
    if not normalized:
        return False
    if re.search(r"[a-z0-9]", normalized):
        pattern = rf"(?<![a-z0-9+#.]){re.escape(normalized)}(?![a-z0-9+#.])"
        return re.search(pattern, blob, re.IGNORECASE) is not None
    return normalized in blob


def _extract_years(parsed: dict | None) -> float | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("years_of_experience", "experience_years", "total_experience_years"):
        value = parsed.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().casefold() for item in value if str(item).strip()]
    if isinstance(value, dict):
        raw = value.get("text") or value.get("value") or value.get("keyword")
        return _normalize_tokens(raw)
    text = str(value).strip()
    if not text:
        return []
    if "," in text or "；" in text or ";" in text:
        parts = re.split(r"[,；;]+", text)
        return [part.strip().casefold() for part in parts if part.strip()]
    return [text.casefold()]


def _hard_value_from_requirement(
    requirement: JobRequirement,
    field: str,
) -> dict[str, Any]:
    """Hard-rule values come from the confirmed JD requirement, never the client."""
    source = (requirement.canonical_label or requirement.raw_text or "").strip()
    if field == "years_experience":
        match = re.search(r"(\d+(?:\.\d+)?)", source)
        if not match:
            raise ValueError("hard_requirement_value_unusable")
        return {"text": match.group(1), "source_text": requirement.raw_text}
    if not source:
        raise ValueError("hard_requirement_value_unusable")
    return {"text": source, "source_text": requirement.raw_text}


def expand_taxonomy_terms(term: str) -> set[str]:
    key = term.strip().casefold()
    aliases = set(_SKILL_ALIASES.get(key, ()))
    aliases.add(key)
    return aliases


def assert_rule_payload_allowed(
    *,
    rule_type: str,
    field: str,
    operator: str,
    value: Any,
    legal_basis_note: str | None,
    employer_confirmed: bool,
    job_requirement_id: str | None,
) -> None:
    sensitive_parts = [
        field,
        operator,
        json.dumps(value, ensure_ascii=False),
        legal_basis_note or "",
    ]
    if any(
        is_sensitive_question(part) or _SENSITIVE_RULE_PATTERN.search(part)
        for part in sensitive_parts
    ):
        raise ValueError("sensitive_rule_rejected")
    if any(_PROHIBITED_PROXY_RULE_PATTERN.search(part) for part in sensitive_parts):
        raise ValueError("prohibited_education_proxy_rule")

    if rule_type == "hard_constraint":
        if field not in HARD_FIELDS:
            raise ValueError("illegal_hard_field")
        if operator not in HARD_OPERATORS[field]:
            raise ValueError("illegal_hard_operator")
        if not employer_confirmed:
            raise ValueError("hard_rule_requires_employer_confirmed")
        if not job_requirement_id:
            raise ValueError("hard_rule_requires_job_requirement")
        if not (legal_basis_note or "").strip():
            raise ValueError("hard_rule_requires_legal_basis_note")
        return

    if rule_type == "keyword":
        if field not in KEYWORD_FIELDS:
            raise ValueError("illegal_keyword_field")
        if operator not in KEYWORD_OPERATORS:
            raise ValueError("illegal_keyword_operator")
        if not _normalize_tokens(value):
            raise ValueError("keyword_value_required")
        return

    if rule_type == "taxonomy":
        if field not in TAXONOMY_FIELDS:
            raise ValueError("illegal_taxonomy_field")
        if operator not in TAXONOMY_OPERATORS:
            raise ValueError("illegal_taxonomy_operator")
        if not _normalize_tokens(value):
            raise ValueError("taxonomy_value_required")
        return

    raise ValueError("illegal_rule_type")


async def _owned_job_or_error(
    db: AsyncSession,
    *,
    job_id: str,
    employer_id: str,
) -> JobDescription:
    job = await db.get(JobDescription, str(job_id))
    if not job or str(job.employer_id) != str(employer_id):
        raise _not_found_error()
    return job


async def _run_for_employer(
    db: AsyncSession,
    *,
    run_id: str,
    employer_id: str,
    for_update: bool = False,
) -> ScreeningRun:
    stmt = select(ScreeningRun).where(ScreeningRun.id == str(run_id))
    if for_update:
        stmt = stmt.with_for_update()
    run = (await db.execute(stmt)).scalars().first()
    if not run or str(run.employer_id) != str(employer_id):
        raise _not_found_error()
    return run


async def create_screening_run(
    db: AsyncSession,
    *,
    employer_id: str,
    job_id: str,
) -> ScreeningRun:
    job = await _owned_job_or_error(db, job_id=job_id, employer_id=employer_id)
    snapshot = await get_or_create_profile(db, job, actor_id=str(employer_id))
    run = ScreeningRun(
        id=str(uuid.uuid4()),
        job_id=str(job.id),
        employer_id=str(employer_id),
        profile_snapshot_id=str(snapshot.id),
        profile_snapshot_hash=snapshot.snapshot_hash,
        status="draft",
        created_by=str(employer_id),
        rules_version=RULES_VERSION,
        keyword_version=KEYWORD_VERSION,
    )
    db.add(run)
    await db.flush()
    return run


async def add_screening_rules(
    db: AsyncSession,
    *,
    employer_id: str,
    run_id: str,
    rules: list[dict[str, Any]],
) -> list[ScreeningRule]:
    run = await _run_for_employer(db, run_id=run_id, employer_id=employer_id, for_update=True)
    # A configured run is immutable. Replays are handled by Idempotency-Key;
    # a second key must not append duplicate or stricter rules.
    if run.status != "draft":
        raise ValueError("run_not_configurable")

    created: list[ScreeningRule] = []
    for index, payload in enumerate(rules):
        rule_type = str(payload.get("rule_type") or "").strip()
        field = str(payload.get("field") or "").strip()
        operator = str(payload.get("operator") or "").strip()
        value = payload.get("value")
        legal_basis_note = payload.get("legal_basis_note")
        employer_confirmed = bool(payload.get("employer_confirmed"))
        job_requirement_id = payload.get("job_requirement_id")
        assert_rule_payload_allowed(
            rule_type=rule_type,
            field=field,
            operator=operator,
            value=value,
            legal_basis_note=legal_basis_note,
            employer_confirmed=employer_confirmed,
            job_requirement_id=job_requirement_id,
        )
        if rule_type == "hard_constraint":
            requirement = await db.get(JobRequirement, str(job_requirement_id))
            if (
                not requirement
                or str(requirement.profile_snapshot_id) != str(run.profile_snapshot_id)
                or not requirement.employer_confirmed
                or not requirement.is_hard_constraint
            ):
                raise ValueError("job_requirement_not_confirmed")
            expected_field = _REQUIREMENT_TYPE_TO_FIELD.get(requirement.requirement_type)
            if requirement.requirement_type in {"task", "other"}:
                expected_field = "required_skill"
            if not expected_field or field != expected_field:
                raise ValueError("hard_field_requirement_mismatch")
            value = _hard_value_from_requirement(requirement, field)
        row = ScreeningRule(
            id=str(uuid.uuid4()),
            run_id=str(run.id),
            rule_type=rule_type,
            field=field,
            operator=operator,
            value=value if isinstance(value, (dict, list)) else {"text": value},
            job_requirement_id=str(job_requirement_id) if job_requirement_id else None,
            employer_confirmed=employer_confirmed if rule_type == "hard_constraint" else False,
            legal_basis_note=(legal_basis_note or "").strip() or None,
            order_no=int(payload.get("order_no") or index),
            enabled=bool(payload.get("enabled", True)),
        )
        db.add(row)
        created.append(row)

    run.status = "configured"
    await db.flush()
    return created


def _compare(operator: str, left: Any, right_tokens: list[str], blob: str) -> bool | None:
    if left is None and operator in {"gte", "lte", "eq"} and not right_tokens:
        return None
    if operator == "gte":
        if left is None or not right_tokens:
            return None
        try:
            return float(left) >= float(right_tokens[0])
        except (TypeError, ValueError):
            return None
    if operator == "lte":
        if left is None or not right_tokens:
            return None
        try:
            return float(left) <= float(right_tokens[0])
        except (TypeError, ValueError):
            return None
    if operator == "eq":
        if not right_tokens:
            return None
        if left is None:
            return True if any(_term_in_blob(blob, token) for token in right_tokens) else None
        if isinstance(left, (dict, list, tuple, set)):
            structured = json.dumps(left, ensure_ascii=False).casefold()
            return any(token in structured for token in right_tokens)
        if isinstance(left, (int, float)):
            try:
                return float(left) == float(right_tokens[0])
            except (TypeError, ValueError, IndexError):
                return None
        left_text = str(left).casefold()
        return left_text in right_tokens or any(token == left_text for token in right_tokens)
    if operator == "contains":
        if not right_tokens:
            return None
        return any(_term_in_blob(blob, token) for token in right_tokens)
    if operator == "in":
        if not right_tokens:
            return None
        if left is None:
            return any(_term_in_blob(blob, token) for token in right_tokens) or None
        if isinstance(left, (dict, list, tuple, set)):
            structured = json.dumps(left, ensure_ascii=False).casefold()
            return any(token in structured for token in right_tokens)
        return str(left).casefold() in right_tokens
    return None


def evaluate_hard_rules(
    *,
    rules: list[ScreeningRule],
    requirements: dict[str, JobRequirement],
    resume_parsed: dict | None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    statuses: list[str] = []
    blob = _text_blob(resume_parsed)
    years = _extract_years(resume_parsed)

    for rule in rules:
        if not rule.enabled or rule.rule_type != "hard_constraint":
            continue
        requirement = requirements.get(str(rule.job_requirement_id or ""))
        if requirement:
            refs.append(
                {
                    "requirement_id": str(requirement.id),
                    "canonical_id": requirement.canonical_id,
                    "canonical_label": requirement.canonical_label,
                    "raw_text": requirement.raw_text,
                    "requirement_type": requirement.requirement_type,
                }
            )
        tokens = _normalize_tokens(rule.value)
        left: Any
        if rule.field == "years_experience":
            left = years
        elif rule.field == "education_level":
            left = (resume_parsed or {}).get("education") or (resume_parsed or {}).get(
                "education_level"
            )
        elif rule.field == "location":
            left = (resume_parsed or {}).get("location")
        elif rule.field == "work_authorization":
            left = (resume_parsed or {}).get("work_authorization")
        elif rule.field == "certificate":
            left = (resume_parsed or {}).get("certificates") or (resume_parsed or {}).get(
                "certifications"
            )
        else:
            left = None
        matched = _compare(rule.operator, left, tokens, blob)
        if matched is None:
            statuses.append("unknown")
            reasons.append(
                {
                    "rule_id": str(rule.id),
                    "field": rule.field,
                    "status": "unknown",
                    "reason": "insufficient_resume_signal",
                    "requirement_id": str(rule.job_requirement_id)
                    if rule.job_requirement_id
                    else None,
                }
            )
        elif matched:
            statuses.append("pass")
            reasons.append(
                {
                    "rule_id": str(rule.id),
                    "field": rule.field,
                    "status": "pass",
                    "requirement_id": str(rule.job_requirement_id)
                    if rule.job_requirement_id
                    else None,
                }
            )
        else:
            statuses.append("fail")
            reasons.append(
                {
                    "rule_id": str(rule.id),
                    "field": rule.field,
                    "status": "fail",
                    "requirement_id": str(rule.job_requirement_id)
                    if rule.job_requirement_id
                    else None,
                }
            )

    if not statuses:
        return "unknown", reasons, refs
    if any(status == "fail" for status in statuses):
        return "fail", reasons, refs
    if any(status == "unknown" for status in statuses):
        return "unknown", reasons, refs
    return "pass", reasons, refs


def evaluate_keyword_and_taxonomy(
    *,
    rules: list[ScreeningRule],
    resume_parsed: dict | None,
) -> list[dict[str, Any]]:
    blob = _text_blob(resume_parsed)
    hits: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.enabled or rule.rule_type not in {"keyword", "taxonomy"}:
            continue
        tokens = _normalize_tokens(rule.value)
        expanded: set[str] = set()
        for token in tokens:
            if rule.rule_type == "taxonomy":
                expanded |= expand_taxonomy_terms(token)
            else:
                expanded.add(token)
        matched_terms = sorted(term for term in expanded if _term_in_blob(blob, term))
        hits.append(
            {
                "rule_id": str(rule.id),
                "rule_type": rule.rule_type,
                "field": rule.field,
                "matched": bool(matched_terms),
                "matched_terms": matched_terms,
                # taxonomy never invents employer requirements
                "adds_requirement": False,
            }
        )
    return hits


def _rules_only_llm_fallback(
    *,
    hard_status: str,
    keyword_hits: list[dict[str, Any]],
    claim_refs: list[dict[str, Any]],
) -> ScreeningLLMOutput:
    missing = [hit for hit in keyword_hits if not hit.get("matched")]
    evidence = []
    if hard_status == "pass":
        evidence.append("硬条件规则未发现明确不满足项（缺数据时不会判 fail）。")
    elif hard_status == "fail":
        evidence.append("至少一条已确认硬条件未匹配；需人工复核，不自动淘汰。")
    else:
        evidence.append("硬条件存在信息不足（unknown），不能视为淘汰。")
    if claim_refs:
        evidence.append(f"已固定 {len(claim_refs)} 条申请 Claim 快照供复核。")
    followups = []
    for hit in missing[:3]:
        terms = ", ".join(hit.get("matched_terms") or []) or "相关关键词"
        followups.append(f"请补充与「{terms}」相关的可验证经历与个人贡献边界。")
    if not followups:
        followups.append("如有关键证据缺口，请候选人补充口径、角色边界或作品材料。")
    return ScreeningLLMOutput(
        evidence_summary=evidence[:5],
        alternative_explanations=[
            "关键词未命中也可能是表述差异，不代表不具备能力。",
            "简历未写明不等于事实缺失。",
        ],
        suggested_followups=followups[:5],
        gap_findings=[f"未命中规则 {hit.get('rule_id')}" for hit in missing[:5]],
        consistency_findings=[],
    )


def _llm_safe_resume(parsed: dict | None) -> dict[str, Any]:
    """Keep professional evidence while excluding contact/basic identity fields."""
    if not isinstance(parsed, dict):
        return {}
    allowed = {
        "summary",
        "skills",
        "work_experience",
        "experience",
        "projects",
        "education",
        "certificates",
        "certifications",
        "achievements",
        "publications",
        "languages",
    }
    return {key: parsed[key] for key in allowed if key in parsed}


def _llm_safe_job(parsed: dict | None) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    allowed = {
        "title",
        "description",
        "responsibilities",
        "requirements",
        "required_skills",
        "preferred_skills",
        "experience_years",
        "education",
        "location",
        "work_mode",
    }
    return {key: parsed[key] for key in allowed if key in parsed}


async def run_screening_llm(
    *,
    resume_parsed: dict | None,
    job_parsed: dict | None,
    hard_status: str,
    keyword_hits: list[dict[str, Any]],
    claim_refs: list[dict[str, Any]],
    actor_id: str,
) -> tuple[ScreeningLLMOutput, dict[str, Any]]:
    meta = {
        "model_called": False,
        "provider_status": "skipped",
        "failure_category": None,
        "prompt_version": SCREENING_PROMPT_VERSION,
    }
    fallback = _rules_only_llm_fallback(
        hard_status=hard_status,
        keyword_hits=keyword_hits,
        claim_refs=claim_refs,
    )
    schema = ScreeningLLMOutput.model_json_schema()
    prompt = {
        "instruction": (
            "你是招聘辅助助手。只输出符合 schema 的 JSON 对象。"
            "只生成证据摘要、替代解释、建议追问与缺口/一致性发现。"
            "禁止输出录用/淘汰结论，禁止修改硬条件状态，禁止指控造假。"
        ),
        "schema": schema,
        "hard_filter_status_readonly": hard_status,
        "keyword_hits": keyword_hits[:20],
        "claim_refs": claim_refs[:20],
        "resume": _llm_safe_resume(resume_parsed),
        "job": _llm_safe_job(job_parsed),
    }
    try:
        meta["model_called"] = True
        result = await gateway_run(
            task="screening_evidence_summary",
            payload={
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only valid JSON matching the provided schema.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt, ensure_ascii=False)[:12000],
                    },
                ],
                "temperature": 0.1,
            },
            schema=ScreeningLLMOutput,
            context=InvocationContext(user_id=str(actor_id), org_id=str(actor_id)),
            require_json=True,
        )
        output = result.parsed
        meta["provider_status"] = "succeeded"
        meta["model_version"] = result.model_id
        return output, meta
    except Exception as exc:
        logger.warning("screening LLM failed: %s", type(exc).__name__)
        meta["provider_status"] = "failed"
        meta["failure_category"] = type(exc).__name__
        return fallback, meta


async def _authorized_applications(
    db: AsyncSession,
    *,
    job_id: str,
    employer_id: str,
) -> list[JobApplication]:
    rows = (
        (
            await db.execute(
                select(JobApplication).where(
                    JobApplication.job_id == str(job_id),
                    JobApplication.employer_id == str(employer_id),
                )
            )
        )
        .scalars()
        .all()
    )
    return [row for row in rows if application_has_candidate_authorization(row)]


async def execute_screening_run(
    db: AsyncSession,
    *,
    employer_id: str,
    run_id: str,
) -> dict[str, Any]:
    run = await _run_for_employer(
        db,
        run_id=run_id,
        employer_id=employer_id,
        for_update=True,
    )
    if run.status == "completed":
        return await serialize_run(db, run)

    job = await _owned_job_or_error(
        db,
        job_id=str(run.job_id),
        employer_id=employer_id,
    )
    snapshot = await db.get(TargetRoleProfileSnapshot, str(run.profile_snapshot_id))
    if not snapshot or snapshot.snapshot_hash != run.profile_snapshot_hash:
        raise ValueError("profile_snapshot_mismatch")

    rules = (
        (
            await db.execute(
                select(ScreeningRule)
                .where(ScreeningRule.run_id == str(run.id), ScreeningRule.enabled.is_(True))
                .order_by(ScreeningRule.order_no, ScreeningRule.created_at)
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        raise ValueError("rules_required")

    requirement_ids = [str(rule.job_requirement_id) for rule in rules if rule.job_requirement_id]
    requirements = {}
    if requirement_ids:
        rows = (
            (await db.execute(select(JobRequirement).where(JobRequirement.id.in_(requirement_ids))))
            .scalars()
            .all()
        )
        requirements = {str(row.id): row for row in rows}

    applications = await _authorized_applications(
        db,
        job_id=str(run.job_id),
        employer_id=employer_id,
    )
    run.status = "running"
    run.executed_at = _utcnow()
    run.candidate_count = len(applications)
    await db.flush()

    existing = {
        str(row.application_id): row
        for row in (
            await db.execute(select(ScreeningResult).where(ScreeningResult.run_id == str(run.id)))
        )
        .scalars()
        .all()
    }

    for application in applications:
        if str(application.id) in existing:
            continue
        application_snapshot = get_resume_snapshot(application)
        if application_snapshot:
            parsed = application_snapshot.get("parsed_json") or {}
            version_id = application_snapshot.get("version_id")
            content_hash = application_snapshot.get("content_hash") or _content_hash(parsed)
            snapshot_status = application_snapshot.get("snapshot_status") or "reliable"
        else:
            # Never fall back to a mutable live resume. Missing legacy snapshots
            # remain unknown and require human review.
            parsed = {}
            version_id = "missing"
            content_hash = _content_hash({})
            snapshot_status = "missing"

        claim_summary = await application_claim_snapshot_summary(db, str(application.id))
        claim_refs = []
        for item in claim_summary or []:
            if not isinstance(item, dict):
                continue
            claim_refs.append(
                {
                    "claim_id": item.get("claim_id") or item.get("id"),
                    "text_snapshot": item.get("text_snapshot") or item.get("current_text"),
                    "evidence_state_snapshot": item.get("evidence_state_snapshot")
                    or item.get("evidence_state"),
                    "workflow_state_snapshot": item.get("workflow_state_snapshot")
                    or item.get("workflow_state"),
                }
            )

        hard_status, hard_reasons, requirement_refs = evaluate_hard_rules(
            rules=list(rules),
            requirements=requirements,
            resume_parsed=parsed if isinstance(parsed, dict) else {},
        )
        keyword_hits = evaluate_keyword_and_taxonomy(
            rules=list(rules),
            resume_parsed=parsed if isinstance(parsed, dict) else {},
        )
        llm_output, llm_meta = await run_screening_llm(
            resume_parsed=parsed if isinstance(parsed, dict) else {},
            job_parsed=job.parsed_json if isinstance(job.parsed_json, dict) else {},
            hard_status=hard_status,
            keyword_hits=keyword_hits,
            claim_refs=claim_refs,
            actor_id=str(employer_id),
        )
        # LLM must never mutate hard_filter_status (re-assert server value)
        frozen_hard_status = hard_status

        trace = DecisionTrace(
            id=str(uuid.uuid4()),
            decision_type="screening_result",
            subject_type="screening_result",
            subject_id="pending",
            observed_source_refs=[
                {
                    "profile_snapshot_id": str(run.profile_snapshot_id),
                    "profile_snapshot_hash": run.profile_snapshot_hash,
                    "resume_version_id": version_id,
                    "resume_content_hash": content_hash,
                    "resume_snapshot_status": snapshot_status,
                    "requirement_refs": requirement_refs,
                    "claim_refs": claim_refs,
                }
            ],
            rules_fired=[
                {
                    "rule_id": str(rule.id),
                    "rule_type": rule.rule_type,
                    "field": rule.field,
                    "operator": rule.operator,
                }
                for rule in rules
            ],
            findings=list(llm_output.gap_findings) + list(llm_output.consistency_findings),
            alternative_explanations=list(llm_output.alternative_explanations),
            uncertainties=[reason for reason in hard_reasons if reason.get("status") == "unknown"]
            + (
                [{"category": "application_snapshot_missing"}]
                if snapshot_status == "missing"
                else []
            ),
            recommended_next_actions=list(llm_output.suggested_followups),
            human_review_required=True,
        )
        db.add(trace)
        await db.flush()

        result = ScreeningResult(
            id=str(uuid.uuid4()),
            run_id=str(run.id),
            application_id=str(application.id),
            hard_filter_status=frozen_hard_status,
            hard_filter_reasons=hard_reasons,
            keyword_hits=keyword_hits,
            evidence_summary=list(llm_output.evidence_summary),
            gap_findings=list(llm_output.gap_findings),
            consistency_findings=list(llm_output.consistency_findings),
            alternative_explanations=list(llm_output.alternative_explanations),
            suggested_followups=list(llm_output.suggested_followups),
            status="pending_review",
            resume_version_id=str(version_id) if version_id else None,
            resume_content_hash=str(content_hash),
            requirement_refs=requirement_refs,
            claim_refs=claim_refs,
            decision_trace_id=str(trace.id),
        )
        trace.subject_id = str(result.id)
        if llm_meta.get("provider_status") == "failed":
            uncertainties = list(trace.uncertainties or [])
            uncertainties.append(
                {
                    "category": "provider_failure",
                    "failure_category": llm_meta.get("failure_category"),
                }
            )
            trace.uncertainties = uncertainties
        if llm_meta.get("model_version"):
            run.model_version = llm_meta["model_version"]

        try:
            async with db.begin_nested():
                db.add(result)
                await db.flush()
        except IntegrityError:
            # Different Idempotency-Key concurrent executes converge on UNIQUE(run_id, application_id).
            existing_row = (
                (
                    await db.execute(
                        select(ScreeningResult).where(
                            ScreeningResult.run_id == str(run.id),
                            ScreeningResult.application_id == str(application.id),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing_row is not None:
                existing[str(application.id)] = existing_row
            continue

    run.status = "completed"
    run.completed_at = _utcnow()
    await db.flush()
    return await serialize_run(db, run)


async def mark_result_reviewed(
    db: AsyncSession,
    *,
    employer_id: str,
    result_id: str,
) -> ScreeningResult:
    result = await db.get(ScreeningResult, str(result_id))
    if not result:
        raise _not_found_error()
    run = await _run_for_employer(
        db,
        run_id=str(result.run_id),
        employer_id=employer_id,
    )
    _ = run
    result.status = "reviewed"
    result.reviewer_id = str(employer_id)
    result.reviewed_at = _utcnow()
    await db.flush()
    return result


async def serialize_trace(trace: DecisionTrace | None) -> dict[str, Any] | None:
    if not trace:
        return None
    return {
        "id": str(trace.id),
        "decision_type": trace.decision_type,
        "subject_type": trace.subject_type,
        "subject_id": str(trace.subject_id),
        "observed_source_refs": trace.observed_source_refs or [],
        "rules_fired": trace.rules_fired or [],
        "findings": trace.findings or [],
        "alternative_explanations": trace.alternative_explanations or [],
        "uncertainties": trace.uncertainties or [],
        "recommended_next_actions": trace.recommended_next_actions or [],
        "human_review_required": bool(trace.human_review_required),
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
    }


async def serialize_result(
    db: AsyncSession,
    result: ScreeningResult,
    *,
    include_trace: bool = True,
) -> dict[str, Any]:
    application = await db.get(JobApplication, str(result.application_id))
    resume_snapshot = get_resume_snapshot(application) if application else None
    resume_parsed = (resume_snapshot or {}).get("parsed_json") or {}
    payload = {
        "id": str(result.id),
        "run_id": str(result.run_id),
        "application_id": str(result.application_id),
        "candidate_name": resume_parsed.get("name") or "候选人",
        "hard_filter_status": result.hard_filter_status,
        "hard_filter_reasons": result.hard_filter_reasons or [],
        "keyword_hits": result.keyword_hits or [],
        "evidence_summary": result.evidence_summary or [],
        "gap_findings": result.gap_findings or [],
        "consistency_findings": result.consistency_findings or [],
        "alternative_explanations": result.alternative_explanations or [],
        "suggested_followups": result.suggested_followups or [],
        "status": result.status,
        "resume_version_id": result.resume_version_id,
        "resume_content_hash": result.resume_content_hash,
        "requirement_refs": result.requirement_refs or [],
        "claim_refs": result.claim_refs or [],
        "reviewer_id": str(result.reviewer_id) if result.reviewer_id else None,
        "reviewed_at": result.reviewed_at.isoformat() if result.reviewed_at else None,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }
    if include_trace and result.decision_trace_id:
        trace = await db.get(DecisionTrace, str(result.decision_trace_id))
        payload["decision_trace"] = await serialize_trace(trace)
    return payload


async def serialize_run(db: AsyncSession, run: ScreeningRun) -> dict[str, Any]:
    rules = (
        (
            await db.execute(
                select(ScreeningRule)
                .where(ScreeningRule.run_id == str(run.id))
                .order_by(ScreeningRule.order_no, ScreeningRule.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": str(run.id),
        "job_id": str(run.job_id),
        "employer_id": str(run.employer_id),
        "profile_snapshot_id": str(run.profile_snapshot_id),
        "profile_snapshot_hash": run.profile_snapshot_hash,
        "status": run.status,
        "candidate_count": run.candidate_count,
        "rules_version": run.rules_version,
        "keyword_version": run.keyword_version,
        "model_version": run.model_version,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "executed_at": run.executed_at.isoformat() if run.executed_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "rules": [
            {
                "id": str(rule.id),
                "rule_type": rule.rule_type,
                "field": rule.field,
                "operator": rule.operator,
                "value": rule.value,
                "job_requirement_id": (
                    str(rule.job_requirement_id) if rule.job_requirement_id else None
                ),
                "employer_confirmed": bool(rule.employer_confirmed),
                "legal_basis_note": rule.legal_basis_note,
                "order_no": rule.order_no,
                "enabled": bool(rule.enabled),
            }
            for rule in rules
        ],
    }


async def list_results_page(
    db: AsyncSession,
    *,
    employer_id: str,
    run_id: str,
    limit: int = 20,
    offset: int = 0,
    hard_status: str | None = None,
    review_status: str | None = None,
) -> dict[str, Any]:
    run = await _run_for_employer(db, run_id=run_id, employer_id=employer_id)
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    conditions = [ScreeningResult.run_id == str(run.id)]
    if hard_status:
        conditions.append(ScreeningResult.hard_filter_status == hard_status)
    if review_status:
        conditions.append(ScreeningResult.status == review_status)
    total = int(
        (await db.execute(select(func.count(ScreeningResult.id)).where(*conditions))).scalar_one()
    )
    page = (
        (
            await db.execute(
                select(ScreeningResult)
                .where(*conditions)
                .order_by(
                    case(
                        (ScreeningResult.status == "pending_review", 0),
                        (ScreeningResult.status == "clarification_requested", 1),
                        else_=2,
                    ),
                    case(
                        (ScreeningResult.hard_filter_status == "fail", 0),
                        (ScreeningResult.hard_filter_status == "unknown", 1),
                        else_=2,
                    ),
                    ScreeningResult.created_at,
                )
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    has_more = offset + len(page) < total
    return {
        "run_id": str(run.id),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "total": total,
        "items": [await serialize_result(db, row, include_trace=False) for row in page],
    }


async def mark_results_reviewed(
    db: AsyncSession,
    *,
    employer_id: str,
    run_id: str,
    result_ids: list[str],
) -> list[ScreeningResult]:
    run = await _run_for_employer(db, run_id=run_id, employer_id=employer_id)
    unique_ids = list(dict.fromkeys(str(item) for item in result_ids))
    if not unique_ids:
        raise ValueError("result_ids_required")
    rows = (
        (
            await db.execute(
                select(ScreeningResult).where(
                    ScreeningResult.run_id == str(run.id),
                    ScreeningResult.id.in_(unique_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(unique_ids):
        raise _not_found_error()
    now = _utcnow()
    for row in rows:
        row.status = "reviewed"
        row.reviewer_id = str(employer_id)
        row.reviewed_at = now
    await db.flush()
    return rows


async def get_result_for_employer(
    db: AsyncSession,
    *,
    employer_id: str,
    result_id: str,
) -> ScreeningResult:
    result = await db.get(ScreeningResult, str(result_id))
    if not result:
        raise _not_found_error()
    await _run_for_employer(
        db,
        run_id=str(result.run_id),
        employer_id=employer_id,
    )
    return result

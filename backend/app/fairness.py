"""Pilot fairness monitoring, proxy audits, and appeal/version closed loop.

Never collects protected demographic attributes. Impact ratio over demographic
groups is computed only when an explicitly consented, de-identified grouping
dataset is provided by operators after legal review.
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .company_registry import infer_role_family
from .models_db import JobApplication, JobDescription, MatchResult, Resume

ASSISTIVE_ONLY_DISCLAIMER = (
    "匹配分、可信度与推荐排序仅为辅助信息，不得用于自动淘汰候选人；"
    "最终录用决定必须由招聘方人工作出。"
)

MIN_SAMPLE_FOR_RATIO = 30
TOP_K_DEFAULT = 10
POSITIVE_PIPELINE_STATUSES = frozenset({"interview_invited", "accepted"})

MATCHING_RULES_VERSION = os.getenv("MATCHING_RULES_VERSION", "hybrid-v2")
CREDIBILITY_RULES_VERSION = os.getenv("CREDIBILITY_RULES_VERSION", "credibility-v1")
RERANK_MODEL_VERSION = os.getenv(
    "RERANK_MODEL_VERSION",
    os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
)


def _bucket_scores(scores: list[float]) -> dict[str, int]:
    buckets = {"0-2": 0, "2-4": 0, "4-6": 0, "6-8": 0, "8-10": 0}
    for score in scores:
        if score < 2:
            buckets["0-2"] += 1
        elif score < 4:
            buckets["2-4"] += 1
        elif score < 6:
            buckets["4-6"] += 1
        elif score < 8:
            buckets["6-8"] += 1
        else:
            buckets["8-10"] += 1
    return buckets


def wilson_interval(successes: int, n: int, z: float = 1.96) -> dict[str, float | None]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return {"low": None, "high": None, "point": None}
    phat = successes / n
    denom = 1 + z * z / n
    centre = phat + z * z / (2 * n)
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return {
        "point": round(phat, 4),
        "low": round(max(0.0, (centre - spread) / denom), 4),
        "high": round(min(1.0, (centre + spread) / denom), 4),
    }


def mean_confidence_interval(values: list[float], z: float = 1.96) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "low": None, "high": None, "n": 0}
    n = len(values)
    m = mean(values)
    if n == 1:
        return {"mean": round(m, 4), "low": round(m, 4), "high": round(m, 4), "n": 1}
    variance = sum((x - m) ** 2 for x in values) / (n - 1)
    se = math.sqrt(variance / n)
    return {
        "mean": round(m, 4),
        "low": round(m - z * se, 4),
        "high": round(m + z * se, 4),
        "n": n,
    }


def impact_ratio(selection_rates: dict[str, float]) -> dict[str, Any]:
    """80% rule style ratios vs the highest group rate."""
    usable = {key: rate for key, rate in selection_rates.items() if rate is not None and rate > 0}
    if len(usable) < 2:
        return {
            "status": "insufficient_groups",
            "ratios": {},
            "reference_group": None,
        }
    reference = max(usable, key=lambda key: usable[key])
    ref_rate = usable[reference]
    ratios = {key: round(rate / ref_rate, 4) if ref_rate else None for key, rate in usable.items()}
    return {
        "status": "computed",
        "reference_group": reference,
        "ratios": ratios,
        "note": "Observational only; not a legal adverse-impact determination.",
    }


def _infer_school_tier(resume_json: dict | None) -> str:
    text_parts: list[str] = []
    data = resume_json or {}
    for key in ("education", "school", "summary"):
        value = data.get(key)
        if isinstance(value, str):
            text_parts.append(value)
        elif isinstance(value, list):
            text_parts.extend(str(item) for item in value)
    blob = " ".join(text_parts)
    for tier in ("985", "211", "双一流"):
        if tier in blob:
            return tier
    return "未标注/其他"


def _infer_region_proxy(resume_json: dict | None, job_json: dict | None) -> str:
    for source in (resume_json or {}, job_json or {}):
        for key in ("location", "city", "region", "expected_location"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:32]
    return "未标注"


def _language_style_proxy(text: str) -> str:
    raw = text or ""
    latin = sum(1 for ch in raw if ("a" <= ch.lower() <= "z"))
    cjk = sum(1 for ch in raw if "\u4e00" <= ch <= "\u9fff")
    total = max(len(raw), 1)
    if latin / total > 0.35:
        return "latin_heavy"
    if cjk / total > 0.35:
        return "cjk_heavy"
    return "mixed_or_short"


def compute_legal_group_impact(
    groups: list[dict[str, Any]],
    *,
    legal_basis_attested: bool,
) -> dict[str, Any]:
    """
    groups item: {group_id, applicants, selected}
    Only computed when operator attests lawful de-identified processing.
    """
    if not legal_basis_attested:
        return {
            "status": "blocked",
            "reason": "缺少合法处理基础证明；不得计算人口组 impact ratio",
            "ratios": {},
        }
    rates: dict[str, float] = {}
    details: list[dict[str, Any]] = []
    for row in groups:
        group_id = str(row.get("group_id") or "unknown")
        applicants = int(row.get("applicants") or 0)
        selected = int(row.get("selected") or 0)
        underpowered = applicants < MIN_SAMPLE_FOR_RATIO
        interval = wilson_interval(selected, applicants)
        details.append(
            {
                "group_id": group_id,
                "applicants": applicants,
                "selected": selected,
                "underpowered": underpowered,
                "selection_rate_ci": interval,
            }
        )
        if not underpowered and applicants > 0:
            rates[group_id] = selected / applicants
    if len(rates) < 2:
        return {
            "status": "insufficient_sample",
            "details": details,
            "ratios": {},
            "reason": f"有效组不足（每组申请数需 ≥ {MIN_SAMPLE_FOR_RATIO}）",
        }
    ratio = impact_ratio(rates)
    return {**ratio, "details": details}


def appeal_and_human_review_channels() -> dict[str, Any]:
    return {
        "clarification_thread": {
            "path": "/applications/{id}/messages",
            "purpose": "候选人说明、更正与补充证据",
        },
        "employer_manual_decision": {
            "path": "/applications/{id}/status",
            "purpose": "招聘方人工复核、邀请或拒绝；系统不得自动淘汰",
        },
        "interview_consent": {
            "path": "/interview/*",
            "purpose": "面试用途同意与结果确认/撤回",
        },
        "privacy_erasure": {
            "path": "/privacy/*",
            "purpose": "更正与删除个人数据入口",
        },
        "policy": "申诉与更正必须由人处理；匹配分不可作为自动拒绝依据",
    }


async def build_fairness_baseline(
    db: AsyncSession,
    *,
    top_k: int = TOP_K_DEFAULT,
    legal_groups: list[dict[str, Any]] | None = None,
    legal_basis_attested: bool = False,
) -> dict[str, Any]:
    match_rows = (
        await db.execute(
            select(
                MatchResult.score,
                MatchResult.job_id,
                MatchResult.resume_id,
                JobDescription.title,
                JobDescription.parsed_json,
            ).join(
                JobDescription,
                JobDescription.id == MatchResult.job_id,
            )
        )
    ).all()

    resume_map = {str(row.id): row for row in (await db.execute(select(Resume))).scalars().all()}

    invite_rows = (
        await db.execute(
            select(
                JobApplication.status,
                JobDescription.title,
            ).join(
                JobDescription,
                JobDescription.id == JobApplication.job_id,
            )
        )
    ).all()

    scores_by_family: dict[str, list[float]] = defaultdict(list)
    for score, _job_id, _resume_id, title, _job_json in match_rows:
        family = infer_role_family(title or "") or "unknown"
        scores_by_family[family].append(float(score))

    by_job: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for score, job_id, _resume_id, title, _job_json in match_rows:
        family = infer_role_family(title or "") or "unknown"
        by_job[str(job_id)].append((float(score), family))

    top_k_hits: dict[str, int] = defaultdict(int)
    top_k_total = 0
    for entries in by_job.values():
        ranked = sorted(entries, key=lambda item: item[0], reverse=True)[:top_k]
        top_k_total += len(ranked)
        for _score, family in ranked:
            top_k_hits[family] += 1

    apps_by_family: dict[str, list[str]] = defaultdict(list)
    for status, title in invite_rows:
        family = infer_role_family(title or "") or "unknown"
        apps_by_family[family].append(str(status or ""))

    families = sorted(set(scores_by_family) | set(apps_by_family) | set(top_k_hits))
    family_stats: list[dict[str, Any]] = []
    for family in families:
        scores = scores_by_family.get(family, [])
        apps = apps_by_family.get(family, [])
        invited = sum(1 for status in apps if status in POSITIVE_PIPELINE_STATUSES)
        invite_rate = (invited / len(apps)) if apps else None
        top_share = (top_k_hits.get(family, 0) / top_k_total) if top_k_total else None
        family_stats.append(
            {
                "role_family": family,
                "match_sample_size": len(scores),
                "application_sample_size": len(apps),
                "mean_score": round(mean(scores), 4) if scores else None,
                "median_score": round(median(scores), 4) if scores else None,
                "score_mean_ci": mean_confidence_interval(scores),
                "invite_rate_ci": wilson_interval(invited, len(apps))
                if apps
                else wilson_interval(0, 0),
                "score_buckets": _bucket_scores(scores) if scores else {},
                "top_k_share": round(top_share, 4) if top_share is not None else None,
                "invite_or_hire_rate": (round(invite_rate, 4) if invite_rate is not None else None),
                "underpowered": len(apps) < MIN_SAMPLE_FOR_RATIO,
            }
        )

    # Proxy-variable audit: school tier / region / language style vs score rank.
    proxy_buckets: dict[str, dict[str, list[float]]] = {
        "school_tier": defaultdict(list),
        "region": defaultdict(list),
        "language_style": defaultdict(list),
    }
    for score, _job_id, resume_id, _title, job_json in match_rows:
        resume = resume_map.get(str(resume_id))
        resume_json = (resume.parsed_json if resume else None) or {}
        proxy_buckets["school_tier"][_infer_school_tier(resume_json)].append(float(score))
        proxy_buckets["region"][_infer_region_proxy(resume_json, job_json or {})].append(
            float(score)
        )
        summary = str(resume_json.get("summary") or "")
        proxy_buckets["language_style"][_language_style_proxy(summary)].append(float(score))

    proxy_audit = {}
    for proxy_name, buckets in proxy_buckets.items():
        proxy_audit[proxy_name] = [
            {
                "bucket": bucket,
                "n": len(values),
                "mean_score": round(mean(values), 4) if values else None,
                "mean_ci": mean_confidence_interval(values),
                "underpowered": len(values) < MIN_SAMPLE_FOR_RATIO,
            }
            for bucket, values in sorted(buckets.items(), key=lambda item: item[0])
        ]

    all_scores = [float(row[0]) for row in match_rows]
    legal_impact = compute_legal_group_impact(
        legal_groups or [],
        legal_basis_attested=legal_basis_attested,
    )

    return {
        "disclaimer": ASSISTIVE_ONLY_DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "auto_reject_forbidden": True,
            "sensitive_attribute_collection": False,
            "labels_are_biased_signals": [
                "employer_useful",
                "interview_invite",
                "historical_hire",
            ],
            "min_sample_for_ratio": MIN_SAMPLE_FOR_RATIO,
            "top_k": top_k,
        },
        "model_versions": {
            "matching_rules": MATCHING_RULES_VERSION,
            "credibility_rules": CREDIBILITY_RULES_VERSION,
            "rerank_model": RERANK_MODEL_VERSION,
        },
        "overall": {
            "match_sample_size": len(all_scores),
            "mean_score": round(mean(all_scores), 4) if all_scores else None,
            "median_score": round(median(all_scores), 4) if all_scores else None,
            "score_mean_ci": mean_confidence_interval(all_scores),
            "score_buckets": _bucket_scores(all_scores) if all_scores else {},
        },
        "by_role_family": family_stats,
        "proxy_variable_audit": proxy_audit,
        "impact_ratio": {
            "status": "not_computed",
            "ratios": {},
            "reference_group": None,
            "reason": (
                "仅在具备合法处理基础的去标识化分组数据上计算；不得用岗位族代替人口统计学分组"
            ),
        },
        "legal_group_impact_ratio": legal_impact,
        "human_review_and_appeals": appeal_and_human_review_channels(),
        "pilot_disclosure": {
            "must_include": [
                "样本量",
                "置信区间或不确定性",
                "已知限制",
                "规则/模型版本",
            ],
            "no_conclusion_when_underpowered": True,
        },
        "limitations": [
            "role_family 是岗位标题代理变量，不是人口统计学分组。",
            "学校层级/地区/语言风格为业务代理变量审计，可能误分类，仅供人工抽查。",
            "样本量不足时 impact_ratio 与代理审计不下结论。",
            "招聘方操作与历史录用带偏差，不可当作真实能力标签。",
        ],
    }

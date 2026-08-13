"""Human-first role, industry and explicit-preference policy for job matching.

The statistical score is only evaluated after this policy answers the question
a person asks first: "Is this plausibly the kind of work I am looking for?"
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


ROLE_TERMS = {
    "data_ai": {
        "data scientist",
        "data analyst",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "research scientist",
        "data labeling",
        "data annotation",
        "data engineer",
        "analytics",
        "business intelligence",
        "数据科学",
        "数据分析",
        "机器学习",
        "人工智能",
        "算法",
        "数据标注",
    },
    "software": {
        "software engineer",
        "software developer",
        "backend",
        "frontend",
        "full stack",
        "fullstack",
        "platform engineer",
        "devops",
        "sre",
        "web developer",
        "cloud developer",
        "cloud engineer",
        "security engineer",
        "developer",
        "软件工程",
        "后端",
        "前端",
        "开发工程师",
        "研发工程师",
    },
    "product_design": {
        "product manager",
        "product designer",
        "ux designer",
        "ui designer",
        "产品经理",
        "产品设计",
        "用户体验",
        "交互设计",
    },
    "research": {
        "research assistant",
        "researcher",
        "scientist",
        "laboratory",
        "研究助理",
        "研究员",
        "科研",
        "实验室",
    },
    "finance_legal": {
        "accountant",
        "controller",
        "auditor",
        "financial analyst",
        "lawyer",
        "legal counsel",
        "finance",
        "financial",
        "payroll",
        "controlling",
        "credit risk",
        "会计",
        "审计",
        "财务",
        "金融分析",
        "法务",
        "律师",
    },
    "people_sales_marketing": {
        "sales",
        "account executive",
        "customer success",
        "recruiter",
        "talent acquisition",
        "marketing",
        "communications",
        "human resources",
        "销售",
        "客户经理",
        "招聘",
        "人才招聘",
        "市场营销",
        "人力资源",
        "公关",
    },
    "operations_admin": {
        "operations",
        "administrator",
        "administrative",
        "receptionist",
        "program coordinator",
        "office manager",
        "executive assistant",
        "project coordinator",
        "运营",
        "行政",
        "前台",
        "项目协调",
    },
    "healthcare": {
        "nurse",
        "physician",
        "medical",
        "clinical",
        "pharmacist",
        "therapist",
        "护士",
        "医生",
        "医疗",
        "临床",
        "药师",
        "治疗师",
    },
    "education_social": {
        "teacher",
        "professor",
        "student support",
        "social worker",
        "veterans",
        "教师",
        "教授",
        "学生事务",
        "社会工作",
        "退伍军人服务",
    },
    "hospitality_recreation": {
        "recreation",
        "culture",
        "hospitality",
        "restaurant",
        "chef",
        "sports",
        "leisure",
        "酒店",
        "餐饮",
        "厨师",
        "体育",
        "文体",
        "休闲",
    },
    "trades_field": {
        "handyman",
        "mechanic",
        "electrician",
        "technician",
        "driver",
        "construction",
        "维修",
        "电工",
        "司机",
        "施工",
        "技工",
    },
}

ROLE_LABELS = {
    "data_ai": "数据与 AI",
    "software": "软件工程",
    "product_design": "产品与设计",
    "research": "研究",
    "finance_legal": "财务/金融/法务",
    "people_sales_marketing": "销售/市场/招聘",
    "operations_admin": "运营与行政",
    "healthcare": "医疗健康",
    "education_social": "教育与社会服务",
    "hospitality_recreation": "文体与服务业",
    "trades_field": "工程技工",
    "unknown": "未识别",
}

ADJACENT_ROLES = {
    frozenset({"data_ai", "software"}),
    frozenset({"data_ai", "research"}),
    frozenset({"software", "product_design"}),
    frozenset({"product_design", "people_sales_marketing"}),
    frozenset({"operations_admin", "people_sales_marketing"}),
    frozenset({"research", "education_social"}),
}

SKILL_ROLE_HINTS = {
    "data_ai": {
        "pandas",
        "numpy",
        "scikit",
        "sklearn",
        "tensorflow",
        "pytorch",
        "machine learning",
        "random forest",
        "regression",
        "r²",
        "mse",
        "statistics",
        "tableau",
        "power bi",
        "数据分析",
        "机器学习",
    },
    "software": {
        "fastapi",
        "django",
        "flask",
        "react",
        "vue",
        "java",
        "spring",
        "postgresql",
        "mysql",
        "redis",
        "docker",
        "kubernetes",
        "api",
    },
}

INDUSTRY_TERMS = {
    "technology": {
        "software",
        "saas",
        "cloud",
        "cybersecurity",
        "人工智能",
        "软件",
        "云计算",
        "科技",
    },
    "finance": {
        "bank",
        "finance",
        "financial",
        "accounting",
        "fintech",
        "trading",
        "insurance",
        "fx",
        "cfd",
        "银行",
        "金融",
        "证券",
        "保险",
        "量化",
        "外汇",
    },
    "healthcare": {"health", "medical", "clinical", "pharma", "医疗", "健康", "临床", "医药"},
    "education_research": {
        "university",
        "education",
        "research",
        "college",
        "大学",
        "教育",
        "研究",
    },
    "climate_energy": {
        "climate",
        "air quality",
        "energy",
        "environment",
        "气候",
        "空气质量",
        "能源",
        "环境",
    },
    "government_public": {"government", "public sector", "veterans", "政府", "公共部门", "国防"},
    "consumer_media": {
        "retail",
        "ecommerce",
        "game",
        "gaming",
        "media",
        "零售",
        "电商",
        "游戏",
        "媒体",
    },
    "manufacturing": {"manufacturing", "automotive", "semiconductor", "制造", "汽车", "半导体"},
}

GENERIC_OR_BROKEN_TITLES = {
    "join us",
    "job details",
    "job posting title",
    "jop posting title",
    "full",
    "free",
    "pushdown",
    "deep ocean",
    "ottawa on",
    "pretty redible",
}


def _plain(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or "")
    return str(value or "")


def _role_scores(text: str) -> dict[str, float]:
    normalized = re.sub(r"\s+", " ", text).casefold()
    scores: dict[str, float] = {}
    for role, terms in ROLE_TERMS.items():
        hits = [term for term in terms if term.casefold() in normalized]
        if hits:
            scores[role] = float(len(hits))
    return scores


def _top_role(scores: dict[str, float]) -> tuple[str, float]:
    if not scores:
        return "unknown", 0.0
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    role, score = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    confidence = min(1.0, 0.45 + score * 0.12 + max(score - second, 0) * 0.08)
    return role, round(confidence, 3)


def infer_candidate_intent(resume: dict) -> dict[str, Any]:
    preferences = resume.get("match_preferences") or {}
    scores: dict[str, float] = defaultdict(float)
    evidence: list[str] = []

    target_roles = preferences.get("target_roles") or []
    explicit = " ".join(_plain(value) for value in target_roles)
    if explicit:
        for role, value in _role_scores(explicit).items():
            scores[role] += value * 12
        evidence.append("用户明确选择的目标岗位")

    expected = str(resume.get("expected_job_title") or "").strip()
    if expected:
        for role, value in _role_scores(expected).items():
            scores[role] += value * 10
        evidence.append("简历意向职位")

    for item in resume.get("work_experience") or []:
        if not isinstance(item, dict):
            continue
        for role, value in _role_scores(str(item.get("position") or "")).items():
            scores[role] += value * 6
    for item in resume.get("projects") or []:
        if not isinstance(item, dict):
            continue
        project_text = " ".join(str(item.get(key) or "") for key in ("name", "role", "description"))
        for role, value in _role_scores(project_text).items():
            scores[role] += value * 2

    skill_text = " ".join(_plain(value) for value in resume.get("skills") or []).casefold()
    project_text = " ".join(
        str(item.get("description") or "")
        for item in resume.get("projects") or []
        if isinstance(item, dict)
    ).casefold()
    combined = f"{skill_text} {project_text}"
    for role, terms in SKILL_ROLE_HINTS.items():
        scores[role] += sum(1.2 for term in terms if term in combined)

    role, confidence = _top_role(dict(scores))
    return {
        "primary_role": role,
        "role_label": ROLE_LABELS[role],
        "confidence": confidence,
        "evidence": evidence or ["根据经历、项目与技能推断"],
        "scores": dict(sorted(scores.items(), key=lambda item: -item[1])[:4]),
    }


def infer_job_role(job: dict, title: str) -> dict[str, Any]:
    title_scores = _role_scores(title or str(job.get("title") or ""))
    role, confidence = _top_role({key: value * 5 for key, value in title_scores.items()})
    source = "title"
    if role == "unknown":
        body = " ".join(str(value) for value in job.get("responsibilities") or [])
        body_scores = _role_scores(body[:6000])
        role, confidence = _top_role(body_scores)
        confidence = round(confidence * 0.75, 3)
        source = "responsibilities"
    return {
        "primary_role": role,
        "role_label": ROLE_LABELS[role],
        "confidence": confidence,
        "source": source,
    }


def infer_industries(text: str) -> list[str]:
    normalized = text.casefold()
    return [
        industry
        for industry, terms in INDUSTRY_TERMS.items()
        if any(term.casefold() in normalized for term in terms)
    ]


def infer_job_industries(job: dict, title: str) -> list[str]:
    """Infer industry only from identity fields, not incidental JD wording.

    Job descriptions routinely mention benefits, office environment, social
    media and customers. Treating those words as the employer's industry made
    cybersecurity and infrastructure roles look like climate or consumer jobs.
    """
    explicit = " ".join(
        _plain(job.get(key))
        for key in ("industry", "industries", "category", "sector")
        if job.get(key)
    )
    identity = " ".join(
        [
            title,
            str(job.get("company_name") or ""),
            explicit,
        ]
    )
    return infer_industries(identity)


def _job_quality(job: dict, title: str, job_role: dict[str, Any]) -> tuple[bool, list[str]]:
    normalized = re.sub(r"\s+", " ", str(title or "")).strip()
    reasons = []
    if normalized.casefold() in GENERIC_OR_BROKEN_TITLES:
        reasons.append("岗位标题是页面噪声或占位词")
    if len(normalized) < 3 or len(normalized) > 180:
        reasons.append("岗位标题长度异常")
    if re.search(r"[ØÙ]{2,}|�", normalized):
        reasons.append("岗位标题存在乱码")
    body = " ".join(str(value) for value in job.get("responsibilities") or [])
    if (
        job_role["primary_role"] == "unknown"
        and len(body.strip()) < 120
        and not (job.get("required_skills") or [])
    ):
        reasons.append("无法从标题或职责识别真实岗位")
    return not reasons, reasons


def apply_preference_policy(
    resume: dict,
    job: dict,
    title: str,
    base_score: float,
    breakdown: dict[str, Any],
) -> tuple[float, dict[str, Any], str]:
    """Apply a selection gate and preference adjustment to a base match."""
    candidate = infer_candidate_intent(resume)
    job_role = infer_job_role(job, title)
    quality_ok, quality_reasons = _job_quality(job, title, job_role)
    preferences = resume.get("match_preferences") or {}
    strictness = str(preferences.get("strictness") or "focused")
    candidate_role = candidate["primary_role"]
    target_role = job_role["primary_role"] if job_role["confidence"] >= 0.55 else "unknown"
    job_role["effective_role"] = target_role
    exact_role = candidate_role != "unknown" and candidate_role == target_role
    adjacent_role = (
        candidate_role != "unknown"
        and target_role != "unknown"
        and frozenset({candidate_role, target_role}) in ADJACENT_ROLES
    )
    adjacent_evidence = sorted(set((breakdown.get("skills") or {}).get("matched") or []))
    adjacent_supported = not adjacent_role or len(adjacent_evidence) >= 2

    resume_blob = " ".join(
        [
            str(resume.get("expected_job_title") or ""),
            str(resume.get("summary") or ""),
            " ".join(
                " ".join(str(item.get(key) or "") for key in ("company", "position", "description"))
                for item in resume.get("work_experience") or []
                if isinstance(item, dict)
            ),
            " ".join(
                " ".join(str(item.get(key) or "") for key in ("name", "role", "description"))
                for item in resume.get("projects") or []
                if isinstance(item, dict)
            ),
        ]
    )
    candidate_industries = list(preferences.get("preferred_industries") or []) or infer_industries(
        resume_blob
    )
    job_industries = infer_job_industries(job, title)
    excluded_industries = set(preferences.get("excluded_industries") or [])
    industry_overlap = sorted(set(candidate_industries) & set(job_industries))

    eligible = quality_ok
    exclusion_reasons = list(quality_reasons)
    if candidate["confidence"] >= 0.6:
        if target_role == "unknown" and strictness != "explore":
            eligible = False
            exclusion_reasons.append("岗位方向无法识别，未进入精准推荐")
        elif strictness == "focused" and not exact_role:
            eligible = False
            exclusion_reasons.append(
                f"精准模式只保留{candidate['role_label']}，该岗位属于{job_role['role_label']}"
            )
        elif strictness == "balanced" and not exact_role and not adjacent_role:
            eligible = False
            exclusion_reasons.append(
                f"目标方向是{candidate['role_label']}，岗位属于{job_role['role_label']}"
            )
        elif strictness == "balanced" and adjacent_role and not adjacent_supported:
            eligible = False
            exclusion_reasons.append("相邻方向未找到至少两项可引用的技能重合")
    if set(job_industries) & excluded_industries:
        eligible = False
        exclusion_reasons.append("命中用户明确排除的行业")
    if preferences.get("preferred_industries") and not industry_overlap and strictness == "focused":
        eligible = False
        exclusion_reasons.append(
            "不在用户选择的目标行业内"
            if job_industries
            else "岗位行业无法验证，未进入目标行业精准推荐"
        )

    role_dimension = dict(breakdown.get("role_match") or {})
    role_weight = float(role_dimension.get("weight") or 2.0)
    old_role_score = float(role_dimension.get("score") or 0.0)
    if exact_role:
        role_ratio = 1.0
    elif adjacent_role:
        role_ratio = 0.7
    else:
        role_ratio = 0.1 if target_role != "unknown" else 0.0
    role_dimension.update(
        {
            "score": round(role_weight * role_ratio, 2),
            "ratio": role_ratio,
            "resume_family": candidate_role,
            "job_family": target_role,
            "family_mismatch": not exact_role,
        }
    )

    industry_dimension = dict(breakdown.get("industry_match") or {})
    industry_weight = float(industry_dimension.get("weight") or 1.0)
    old_industry_score = float(industry_dimension.get("score") or 0.0)
    if industry_overlap:
        industry_ratio = 1.0
    elif not job_industries:
        industry_ratio = 0.5
    else:
        industry_ratio = 0.2
    industry_dimension.update(
        {
            "score": round(industry_weight * industry_ratio, 2),
            "ratio": industry_ratio,
            "resume_industries": candidate_industries,
            "job_industries": job_industries,
            "overlap": industry_overlap,
        }
    )

    corrected_base = (
        base_score
        - old_role_score
        - old_industry_score
        + role_dimension["score"]
        + industry_dimension["score"]
    )
    adjustment = 0.0
    positive_reasons = []
    if exact_role:
        adjustment += 0.3
        positive_reasons.append(f"岗位方向与{candidate['role_label']}目标一致")
    elif adjacent_role and adjacent_supported:
        adjustment += 0.1
        positive_reasons.append("岗位属于可迁移的相邻方向")
    if industry_overlap:
        adjustment += 0.2
        positive_reasons.append(f"行业语境重合：{'、'.join(industry_overlap[:2])}")
    elif candidate_industries and job_industries:
        adjustment -= 0.8

    score = round(max(0.0, min(10.0, corrected_base + adjustment)), 1)
    if not eligible:
        score = min(score, 2.5)
    preference_meta = {
        "eligible": eligible,
        "strictness": strictness,
        "candidate_intent": candidate,
        "job_role": job_role,
        "role_relation": "exact" if exact_role else ("adjacent" if adjacent_role else "different"),
        "adjacent_evidence": adjacent_evidence,
        "adjacent_supported": adjacent_supported,
        "candidate_industries": candidate_industries,
        "job_industries": job_industries,
        "industry_overlap": industry_overlap,
        "quality_passed": quality_ok,
        "exclusion_reasons": exclusion_reasons,
        "score_adjustment": round(adjustment, 2),
    }
    updated = dict(breakdown)
    updated.update(
        {
            "source": "human_preference_v3",
            "version": 3,
            "total": score,
            "role_match": role_dimension,
            "industry_match": industry_dimension,
            "preference_policy": preference_meta,
        }
    )
    if eligible:
        reason = "；".join(positive_reasons) or "岗位通过职业方向与质量门槛"
    else:
        reason = "不进入精准推荐：" + "；".join(exclusion_reasons[:3])
    return score, updated, reason

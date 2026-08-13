"""
Hybrid Match v2 — Layer 2 可解释六维评分。

六维权重（合计 100%）：
  技能 35% | 职位方向 20% | 经验 15% | 地点 5% | 薪资 5% | 学历 10% | 软实力 10%

对外主入口：hybrid_score(resume_json, job_json, job_title=None)
返回：(total_score, breakdown, potential_score, match_tier)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .company_registry import (
    LEADERSHIP_KEYWORDS,
    SOFT_SKILL_KEYWORDS,
    infer_role_family,
    normalize_skill_name,
)
from .matching_signals import compute_supplementary_signals
from .career_suggestions import generate_career_suggestions

# v1 六维权重（保留兼容）
WEIGHTS = {
    "skills": 3.5,
    "title": 2.0,
    "experience": 1.5,
    "location": 0.5,
    "salary": 0.5,
    "education": 1.0,
    "soft_skills": 1.0,
}

# v2 十维权重（意见稿 v2.0，职位方向加重）
V2_WEIGHTS = {
    "skills": 2.0,
    "experience": 1.5,
    "role_match": 2.0,
    "industry_match": 1.0,
    "education": 0.5,
    "location": 0.5,
    "salary": 0.5,
    "impact": 1.0,
    "soft_skills": 0.5,
    "growth_potential": 1.0,
}

# 岗位描述里的通用噪声词，不能当作软实力差距
SOFT_SKILL_NOISE = {
    "任职要求",
    "岗位职责",
    "其他任务",
    "相关专业",
    "专业知识",
    "以上学历",
    "工作经验",
    "能力要求",
    "任职",
    "要求",
    "负责",
    "完成",
    "进行",
    "开展",
    "以及",
    "相关",
    "工作",
    "岗位",
    "人员",
    "条件",
    "优先",
    "熟悉",
    "具有",
    "具备",
    "良好",
    "以上",
    "以下",
    "本科",
    "硕士",
    "博士",
    "学历",
}

# 可视为同一大类的职位方向（其余组合会触发降分）
ROLE_FAMILY_COMPATIBLE = {
    frozenset({"engineering", "data"}),
    frozenset({"management", "product"}),
}

# 各维度在 0~10 分制下的满分贡献（v1）

# 职位标题同义词组（同一组内视为相关）
TITLE_SYNONYM_GROUPS = [
    {"后端", "backend", "服务端", "server", "java开发", "java 开发", "python开发", "golang开发"},
    {"前端", "frontend", "web开发", "react开发", "vue开发"},
    {"算法", "机器学习", "ml", "ai工程师", "nlp"},
    {"产品", "产品经理", "pm", "product manager"},
    {"数据", "数据分析", "数据分析师", "bi"},
    {"测试", "qa", "质量", "测试工程师"},
    {"运维", "devops", "sre", "运维工程师"},
]

EDUCATION_RANK = {
    "博士": 4,
    "phd": 4,
    "硕士": 3,
    "研究生": 3,
    "master": 3,
    "本科": 2,
    "学士": 2,
    "bachelor": 2,
    "大专": 1,
    "专科": 1,
    "associate": 1,
}


def _extract_skill_names(skill_list, *, include_planned: bool = False) -> Set[str]:
    """Extract current capability skill names.

    Skills tagged ``planned`` are future learning intents and must not count as
    current capability unless ``include_planned`` is explicitly True (used only
    for counterfactual potential scoring).
    """
    skills: Set[str] = set()
    for s in skill_list or []:
        if isinstance(s, dict):
            level = str(s.get("level") or "").strip().lower()
            if level == "planned" and not include_planned:
                continue
            name = normalize_skill_name(s.get("name", ""))
        else:
            name = normalize_skill_name(str(s))
        if name:
            skills.add(name)
    return skills


def _skill_match_score(
    resume_skills: Set[str], required_skills: Set[str]
) -> Tuple[float, List[str], List[str]]:
    """技能命中 0~1，支持部分包含（如 spring boot ⊃ spring）。"""
    if not required_skills:
        return 1.0, [], []

    matched: List[str] = []
    missing: List[str] = []
    credit = 0.0

    for req in required_skills:
        hit = False
        for rs in resume_skills:
            if req == rs or req in rs or rs in req:
                matched.append(req)
                hit = True
                break
        if not hit:
            missing.append(req)
        else:
            credit += 1.0

    return credit / len(required_skills), sorted(set(matched)), sorted(missing)


def _tokenize_title(text: str) -> Set[str]:
    if not text:
        return set()
    t = text.lower().strip()
    tokens = set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", t))
    tokens.add(t)
    return tokens


def _expand_title_tokens(tokens: Set[str]) -> Set[str]:
    expanded = set(tokens)
    for group in TITLE_SYNONYM_GROUPS:
        if tokens & group:
            expanded |= group
    return expanded


def _role_families_compatible(family_a: str, family_b: str) -> bool:
    if family_a == family_b:
        return True
    if family_a == "general" or family_b == "general":
        return True
    return frozenset({family_a, family_b}) in ROLE_FAMILY_COMPATIBLE


def _score_title(resume_title: str, job_title: str) -> float:
    """职位方向 0~1：关键词重叠 + 同义词组 + 职位大类校验。"""
    if not job_title:
        return 1.0
    if not resume_title:
        return 0.35

    r_tokens = _expand_title_tokens(_tokenize_title(resume_title))
    j_tokens = _expand_title_tokens(_tokenize_title(job_title))

    if not j_tokens:
        return 1.0

    overlap = len(r_tokens & j_tokens)
    if overlap == 0:
        rl, jl = resume_title.lower(), job_title.lower()
        if rl in jl or jl in rl:
            base = 0.55
        else:
            base = 0.15
    else:
        base = min(overlap / max(len(j_tokens), 1), 1.0)

    resume_family = infer_role_family(resume_title)
    job_family = infer_role_family(job_title)
    if resume_family != "general" and job_family != "general":
        if not _role_families_compatible(resume_family, job_family):
            base = min(base, 0.2)

    return base


def _role_direction_penalty(
    resume_title: str, job_title: str, title_ratio: float
) -> Tuple[float, dict]:
    """职位方向明显不符时额外扣分（防止技能分拉高总分）。"""
    resume_family = infer_role_family(resume_title or "")
    job_family = infer_role_family(job_title or "")
    meta = {
        "resume_family": resume_family,
        "job_family": job_family,
        "family_mismatch": False,
        "penalty": 0.0,
    }

    penalty = 0.0
    if title_ratio < 0.35:
        penalty += round((0.35 - title_ratio) * 4.0, 2)

    if (
        resume_family != "general"
        and job_family != "general"
        and not _role_families_compatible(resume_family, job_family)
    ):
        meta["family_mismatch"] = True
        penalty += 2.0

    meta["penalty"] = round(penalty, 2)
    return penalty, meta


def _score_experience(resume_json: dict, job_json: dict) -> Tuple[float, float, Optional[int]]:
    """经验年限 0~1，平滑曲线。"""
    total_years = sum(
        float(exp.get("duration_years") or 0)
        for exp in resume_json.get("work_experience") or []
        if isinstance(exp, dict)
    )
    required = job_json.get("experience_years")
    if required is None or required <= 0:
        return 1.0, total_years, None

    ratio = total_years / required
    if ratio >= 1.0:
        score = 1.0
    elif ratio >= 0.5:
        score = 0.5 + (ratio - 0.5)  # 0.5~1.0 线性
    else:
        score = ratio  # 0~0.5 线性

    return min(score, 1.0), total_years, int(required)


def _score_location(resume_json: dict, job_json: dict) -> float:
    """地点 0~1 梯度（非硬 0/1）。"""
    resume_loc = (resume_json.get("location_preference") or "").lower().strip()
    job_loc = (job_json.get("location") or "").lower().strip()

    if not job_loc or not resume_loc:
        return 0.85

    if "远程" in resume_loc or "全国" in job_loc or "remote" in resume_loc:
        return 1.0
    if job_loc in resume_loc or resume_loc in job_loc:
        return 1.0

    # 同城不同区 / 同省
    r_city = resume_loc[:2]
    j_city = job_loc[:2]
    if r_city and r_city == j_city:
        return 0.6

    return 0.0


def _parse_salary_range(text) -> Optional[Tuple[float, float]]:
    if not text:
        return None
    nums = re.findall(r"\d+\.?\d*", str(text))
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    if len(nums) == 1:
        v = float(nums[0])
        return v, v
    return None


def _score_salary(resume_json: dict, job_json: dict) -> float:
    """薪资 0~1：区间交集比例。"""
    resume_range = _parse_salary_range(resume_json.get("expected_salary"))
    job_range = _parse_salary_range(job_json.get("salary_range"))

    if not resume_range or not job_range:
        return 0.85

    rmin, rmax = resume_range
    jmin, jmax = job_range
    if rmin > rmax:
        rmin, rmax = rmax, rmin
    if jmin > jmax:
        jmin, jmax = jmax, jmin

    overlap_start = max(rmin, jmin)
    overlap_end = min(rmax, jmax)
    if overlap_end < overlap_start:
        gap = overlap_start - overlap_end
        span = max(jmax - jmin, 1.0)
        return max(0.0, 1.0 - gap / span)

    overlap = overlap_end - overlap_start
    job_span = max(jmax - jmin, 1.0)
    return min(overlap / job_span + 0.3, 1.0)


def _parse_education_rank(text: str) -> int:
    if not text:
        return 0
    t = text.lower()
    best = 0
    for key, rank in EDUCATION_RANK.items():
        if key in t:
            best = max(best, rank)
    return best


def _score_education(resume_json: dict, job_json: dict) -> float:
    """学历 0~1。"""
    req_text = job_json.get("education_requirement") or job_json.get("education") or ""
    resume_text = resume_json.get("education") or resume_json.get("degree") or ""

    req_rank = _parse_education_rank(req_text)
    resume_rank = _parse_education_rank(resume_text)

    if req_rank == 0:
        return 1.0
    if resume_rank == 0:
        return 0.4
    if resume_rank >= req_rank:
        return 1.0
    return max(resume_rank / req_rank, 0.2)


def _collect_resume_text(resume_json: dict) -> str:
    parts = [
        resume_json.get("summary") or "",
        resume_json.get("education") or "",
    ]
    for exp in resume_json.get("work_experience") or []:
        if isinstance(exp, dict):
            parts.append(exp.get("description") or "")
    return " ".join(parts).lower()


def _extract_job_soft_requirements(job_json: dict) -> Set[str]:
    """从 JD 结构化字段 + 预定义软实力词表提取要求，避免切碎中文造成噪声。"""
    required: Set[str] = set()

    for s in job_json.get("soft_skills") or []:
        name = str(s).strip()
        if name and name not in SOFT_SKILL_NOISE and len(name) >= 2:
            required.add(name)

    for s in job_json.get("leadership_signals") or []:
        name = str(s).strip()
        if name and name not in SOFT_SKILL_NOISE and len(name) >= 2:
            required.add(name)

    resp_text = " ".join(str(r) for r in job_json.get("responsibilities") or [])
    for kw in SOFT_SKILL_KEYWORDS + LEADERSHIP_KEYWORDS:
        if kw in resp_text and kw not in SOFT_SKILL_NOISE:
            required.add(kw)

    return required


def _score_soft_skills(resume_json: dict, job_json: dict) -> Tuple[float, List[str]]:
    """软实力 0~1：仅匹配预定义词表与 JD 结构化字段。"""
    required = _extract_job_soft_requirements(job_json)
    if not required:
        return 1.0, []

    resume_soft = set(resume_json.get("soft_skills") or [])
    resume_text = _collect_resume_text(resume_json)

    matched = 0
    missing: List[str] = []
    for req in sorted(required):
        if req in resume_soft or req.lower() in resume_text:
            matched += 1
        else:
            missing.append(req)

    score = matched / len(required)
    return score, missing[:8]


def _skills_from_responsibilities(job_json: dict) -> Set[str]:
    """从岗位职责里抽取技术关键词，补充 required_skills。"""
    extra: Set[str] = set()
    tech_pattern = re.compile(
        r"\b(java|python|go|golang|react|vue|spring|mysql|redis|kafka|docker|kubernetes|k8s|aws|sql)\b",
        re.I,
    )
    for resp in job_json.get("responsibilities") or []:
        for m in tech_pattern.findall(str(resp)):
            extra.add(normalize_skill_name(m))
    return extra


def _match_tier(total: float) -> str:
    if total >= 8.0:
        return "high"
    if total >= 5.0:
        return "medium"
    return "low"


def _build_reason(breakdown: dict, total: float) -> str:
    """生成可读的匹配理由（替代「快速评估」一句话）。"""
    parts = []
    dim_labels = {
        "skills": "技能",
        "title": "职位方向",
        "experience": "经验",
        "location": "地点",
        "salary": "薪资",
        "education": "学历",
        "soft_skills": "软实力",
    }
    for key, label in dim_labels.items():
        dim = breakdown.get(key, {})
        ratio = dim.get("ratio", 0)
        if ratio >= 0.8:
            parts.append(f"{label}匹配良好")
        elif ratio < 0.5:
            parts.append(f"{label}偏弱")

    skills = breakdown.get("skills", {})
    missing = skills.get("missing") or []
    if missing:
        parts.append(f"缺 {', '.join(missing[:3])}")

    if not parts:
        return f"综合匹配 {total}/10"
    return f"综合 {total}/10：" + "；".join(parts[:4])


def _compute_weighted_total(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str],
) -> Tuple[float, dict, List[str], List[str]]:
    """计算各维得分与 breakdown（不算 potential）。"""
    resume_skills = _extract_skill_names(resume_json.get("skills"))
    required_skills = _extract_skill_names(job_json.get("required_skills"))
    required_skills |= _skills_from_responsibilities(job_json)

    skill_ratio, matched_skills, missing_skills = _skill_match_score(resume_skills, required_skills)
    resume_title = resume_json.get("expected_job_title") or ""
    job_title_str = job_title or job_json.get("title") or ""
    title_ratio = _score_title(resume_title, job_title_str)
    exp_ratio, years, req_years = _score_experience(resume_json, job_json)
    loc_ratio = _score_location(resume_json, job_json)
    sal_ratio = _score_salary(resume_json, job_json)
    edu_ratio = _score_education(resume_json, job_json)
    soft_ratio, soft_missing = _score_soft_skills(resume_json, job_json)

    weighted = {
        "skills": round(skill_ratio * WEIGHTS["skills"], 2),
        "title": round(title_ratio * WEIGHTS["title"], 2),
        "experience": round(exp_ratio * WEIGHTS["experience"], 2),
        "location": round(loc_ratio * WEIGHTS["location"], 2),
        "salary": round(sal_ratio * WEIGHTS["salary"], 2),
        "education": round(edu_ratio * WEIGHTS["education"], 2),
        "soft_skills": round(soft_ratio * WEIGHTS["soft_skills"], 2),
    }
    subtotal = round(min(sum(weighted.values()), 10.0), 1)
    role_penalty, role_meta = _role_direction_penalty(resume_title, job_title_str, title_ratio)
    total = round(max(subtotal - role_penalty, 0.0), 1)

    breakdown = {
        "source": "hybrid",
        "total": total,
        "subtotal_before_role_penalty": subtotal,
        "role_direction_penalty": role_penalty,
        "skills": {
            "score": weighted["skills"],
            "ratio": round(skill_ratio, 3),
            "weight": WEIGHTS["skills"],
            "matched": matched_skills,
            "missing": missing_skills,
        },
        "title": {
            "score": weighted["title"],
            "ratio": round(title_ratio, 3),
            "weight": WEIGHTS["title"],
            **role_meta,
        },
        "experience": {
            "score": weighted["experience"],
            "ratio": round(exp_ratio, 3),
            "weight": WEIGHTS["experience"],
            "years": years,
            "required": req_years,
        },
        "location": {
            "score": weighted["location"],
            "ratio": round(loc_ratio, 3),
            "weight": WEIGHTS["location"],
        },
        "salary": {
            "score": weighted["salary"],
            "ratio": round(sal_ratio, 3),
            "weight": WEIGHTS["salary"],
        },
        "education": {
            "score": weighted["education"],
            "ratio": round(edu_ratio, 3),
            "weight": WEIGHTS["education"],
        },
        "soft_skills": {
            "score": weighted["soft_skills"],
            "ratio": round(soft_ratio, 3),
            "weight": WEIGHTS["soft_skills"],
            "missing": soft_missing,
        },
    }
    return total, breakdown, missing_skills, soft_missing


def hybrid_score(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str] = None,
) -> Tuple[float, Dict, float, str]:
    """
    六维混合评分。

    Returns:
        total_score: 0~10
        breakdown: 各维明细（含 matched / missing）
        potential_score: 补齐 missing 技能/软实力后的估算分
        match_tier: high / medium / low
    """
    if not resume_json or not job_json:
        empty = {"source": "hybrid", "total": 5.0, "dimensions": {}}
        return 5.0, empty, 5.0, "medium"

    total, breakdown, missing_skills, soft_missing = _compute_weighted_total(
        resume_json, job_json, job_title
    )

    potential_score = _estimate_potential_score(
        resume_json, job_json, job_title, missing_skills, soft_missing, total
    )
    tier = _match_tier(total)
    breakdown["match_tier"] = tier
    breakdown["potential_score"] = potential_score
    breakdown["improvement_delta"] = round(potential_score - total, 1)

    return total, breakdown, potential_score, tier


def _estimate_potential_score(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str],
    missing_skills: List[str],
    soft_missing: List[str],
    current_total: float,
) -> float:
    """Counterfactual score if missing skills were acquired.

    Future skills are stored as ``planned`` and never treated as current
    capability on the real resume. Only this ephemeral scoring copy maps
    planned → temporary proficiency for the potential number.
    """
    if not missing_skills and not soft_missing:
        return current_total

    hypothetical = dict(resume_json)
    hypo_skills = list(hypothetical.get("skills") or [])
    existing = _extract_skill_names(hypo_skills, include_planned=True)
    for sk in missing_skills:
        if sk not in existing:
            hypo_skills.append({"name": sk, "level": "planned"})
    scoring_skills = [
        (
            {**s, "level": "intermediate"}
            if isinstance(s, dict) and str(s.get("level") or "").lower() == "planned"
            else s
        )
        for s in hypo_skills
    ]
    hypothetical["skills"] = scoring_skills

    hypo_soft = list(hypothetical.get("soft_skills") or [])
    for s in soft_missing:
        if s not in hypo_soft:
            hypo_soft.append(s)
    hypothetical["soft_skills"] = hypo_soft

    potential, _, _, _ = _compute_weighted_total(hypothetical, job_json, job_title)
    return potential


def build_match_reason(breakdown: dict, total: float) -> str:
    """供 matching.py 在 Step 1.2 接入时使用。"""
    return _build_reason(breakdown, total)


def build_match_reason_v2(breakdown: dict, total: float) -> str:
    """v2 可读理由（无 signals 时使用）。"""
    return _build_reason_v2(breakdown, total, {})


def _compute_v2_total(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str],
    *,
    include_planned: bool = False,
) -> Tuple[float, dict, List[str], List[str], dict]:
    """v2 十维评分。"""
    from .matching_signals import score_industry_match, score_impact, score_growth_potential

    resume_skills = _extract_skill_names(resume_json.get("skills"), include_planned=include_planned)
    required_skills = _extract_skill_names(job_json.get("required_skills"))
    required_skills |= _skills_from_responsibilities(job_json)

    skill_ratio, matched_skills, missing_skills = _skill_match_score(resume_skills, required_skills)
    resume_title = resume_json.get("expected_job_title") or ""
    job_title_str = job_title or job_json.get("title") or ""
    title_ratio = _score_title(resume_title, job_title_str)
    exp_ratio, years, req_years = _score_experience(resume_json, job_json)
    ind_ratio, ind_detail = score_industry_match(resume_json, job_json, job_title or "")
    loc_ratio = _score_location(resume_json, job_json)
    sal_ratio = _score_salary(resume_json, job_json)
    edu_ratio = _score_education(resume_json, job_json)
    impact_ratio, impact_detail = score_impact(resume_json)
    soft_ratio, soft_missing = _score_soft_skills(resume_json, job_json)
    growth_ratio, growth_detail = score_growth_potential(resume_json, job_json, job_title or "")

    weighted = {
        "skills": round(skill_ratio * V2_WEIGHTS["skills"], 2),
        "experience": round(exp_ratio * V2_WEIGHTS["experience"], 2),
        "role_match": round(title_ratio * V2_WEIGHTS["role_match"], 2),
        "industry_match": round(ind_ratio * V2_WEIGHTS["industry_match"], 2),
        "education": round(edu_ratio * V2_WEIGHTS["education"], 2),
        "location": round(loc_ratio * V2_WEIGHTS["location"], 2),
        "salary": round(sal_ratio * V2_WEIGHTS["salary"], 2),
        "impact": round(impact_ratio * V2_WEIGHTS["impact"], 2),
        "soft_skills": round(soft_ratio * V2_WEIGHTS["soft_skills"], 2),
        "growth_potential": round(growth_ratio * V2_WEIGHTS["growth_potential"], 2),
    }
    subtotal = round(min(sum(weighted.values()), 10.0), 1)
    role_penalty, role_meta = _role_direction_penalty(resume_title, job_title_str, title_ratio)
    total = round(max(subtotal - role_penalty, 0.0), 1)

    breakdown = {
        "source": "hybrid_v2",
        "version": 2,
        "total": total,
        "subtotal_before_role_penalty": subtotal,
        "role_direction_penalty": role_penalty,
        "skills": {
            "score": weighted["skills"],
            "ratio": round(skill_ratio, 3),
            "weight": V2_WEIGHTS["skills"],
            "matched": matched_skills,
            "missing": missing_skills,
        },
        "experience": {
            "score": weighted["experience"],
            "ratio": round(exp_ratio, 3),
            "weight": V2_WEIGHTS["experience"],
            "years": years,
            "required": req_years,
        },
        "role_match": {
            "score": weighted["role_match"],
            "ratio": round(title_ratio, 3),
            "weight": V2_WEIGHTS["role_match"],
            **role_meta,
        },
        "industry_match": {
            "score": weighted["industry_match"],
            "ratio": round(ind_ratio, 3),
            "weight": V2_WEIGHTS["industry_match"],
            **{k: v for k, v in ind_detail.items() if k != "ratio"},
        },
        "education": {
            "score": weighted["education"],
            "ratio": round(edu_ratio, 3),
            "weight": V2_WEIGHTS["education"],
        },
        "location": {
            "score": weighted["location"],
            "ratio": round(loc_ratio, 3),
            "weight": V2_WEIGHTS["location"],
        },
        "salary": {
            "score": weighted["salary"],
            "ratio": round(sal_ratio, 3),
            "weight": V2_WEIGHTS["salary"],
        },
        "impact": {
            "score": weighted["impact"],
            "ratio": round(impact_ratio, 3),
            "weight": V2_WEIGHTS["impact"],
            **{k: v for k, v in impact_detail.items() if k != "ratio"},
        },
        "soft_skills": {
            "score": weighted["soft_skills"],
            "ratio": round(soft_ratio, 3),
            "weight": V2_WEIGHTS["soft_skills"],
            "missing": soft_missing,
        },
        "growth_potential": {
            "score": weighted["growth_potential"],
            "ratio": round(growth_ratio, 3),
            "weight": V2_WEIGHTS["growth_potential"],
            **{k: v for k, v in growth_detail.items() if k != "ratio"},
        },
    }
    signals_preview = {
        "impact_weak": not impact_detail.get("has_quantified_impact", True),
        "industry_mismatch": ind_ratio < 0.5,
    }
    return total, breakdown, missing_skills, soft_missing, signals_preview


def hybrid_score_v2(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str] = None,
    *,
    include_planned: bool = False,
) -> Tuple[float, Dict, float, str]:
    """v2 十维混合评分（含 industry / impact / growth）。

    ``include_planned`` is only for explicit counterfactual scoring (e.g. PR9
    capability scenarios). Current capability scoring must leave it False.
    """
    if not resume_json or not job_json:
        empty = {"source": "hybrid_v2", "total": 5.0}
        return 5.0, empty, 5.0, "medium"

    total, breakdown, missing_skills, soft_missing, _ = _compute_v2_total(
        resume_json, job_json, job_title, include_planned=include_planned
    )
    potential = _estimate_potential_score_v2(
        resume_json, job_json, job_title, missing_skills, soft_missing, total
    )
    tier = _match_tier(total)
    breakdown["match_tier"] = tier
    breakdown["potential_score"] = potential
    breakdown["improvement_delta"] = round(potential - total, 1)
    return total, breakdown, potential, tier


def _estimate_potential_score_v2(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str],
    missing_skills: List[str],
    soft_missing: List[str],
    current_total: float,
) -> float:
    if not missing_skills and not soft_missing:
        return current_total
    hypothetical = dict(resume_json)
    hypo_skills = list(hypothetical.get("skills") or [])
    existing = _extract_skill_names(hypo_skills, include_planned=True)
    for sk in missing_skills:
        if sk not in existing:
            hypo_skills.append({"name": sk, "level": "planned"})
    # Ephemeral scoring copy only — planned must not become current capability.
    hypothetical["skills"] = [
        (
            {**s, "level": "intermediate"}
            if isinstance(s, dict) and str(s.get("level") or "").lower() == "planned"
            else s
        )
        for s in hypo_skills
    ]
    hypo_soft = list(hypothetical.get("soft_skills") or [])
    for s in soft_missing:
        if s not in hypo_soft:
            hypo_soft.append(s)
    hypothetical["soft_skills"] = hypo_soft
    potential, _, _, _, _ = _compute_v2_total(hypothetical, job_json, job_title)
    return potential


def full_match_evaluation(
    resume_json: dict,
    job_json: dict,
    job_title: Optional[str] = None,
) -> dict:
    """
    完整匹配评估：v2 评分 + 补充信号 + 职业建议。

    职业建议由评分系统生成，供简历工作台展示/采纳。
    """
    total, breakdown, potential, tier = hybrid_score_v2(resume_json, job_json, job_title)

    missing_skills = breakdown.get("skills", {}).get("missing") or []
    known_skills = set(breakdown.get("skills", {}).get("matched") or [])

    signals = compute_supplementary_signals(
        resume_json,
        job_json,
        job_title or "",
        missing_skills=missing_skills,
        known_skills=known_skills,
    )
    suggestions = generate_career_suggestions(
        resume_json,
        job_json,
        job_title or "",
        missing_skills=missing_skills,
        impact_weak=not signals["impact"].get("has_quantified_impact", True),
        industry_mismatch=signals["industry_match"]["ratio"] < 0.5,
    )

    reason = _build_reason_v2(breakdown, total, signals)

    return {
        "match_score": total,
        "potential_score": potential,
        "improvement_delta": breakdown.get("improvement_delta", 0),
        "match_tier": tier,
        "skill_gap": missing_skills,
        "breakdown": breakdown,
        "signals": signals,
        "career_suggestions": suggestions,
        "reason": reason,
    }


def _build_reason_v2(breakdown: dict, total: float, signals: dict) -> str:
    parts = []
    dim_labels = {
        "skills": "技能",
        "role_match": "职位方向",
        "industry_match": "行业",
        "experience": "经验",
        "impact": "项目影响力",
        "growth_potential": "成长潜力",
    }
    for key, label in dim_labels.items():
        dim = breakdown.get(key, {})
        ratio = dim.get("ratio", 0)
        if ratio >= 0.8:
            parts.append(f"{label}匹配良好")
        elif ratio < 0.5:
            parts.append(f"{label}偏弱")

    missing = breakdown.get("skills", {}).get("missing") or []
    if missing:
        parts.append(f"简历中未找到 {', '.join(missing[:3])}，需确认")

    role_dim = breakdown.get("role_match") or breakdown.get("title") or {}
    if role_dim.get("family_mismatch"):
        parts.append("职位大类不符")
    elif role_dim.get("ratio", 1) < 0.35:
        parts.append("职位方向偏差大")

    if breakdown.get("role_direction_penalty", 0) >= 1.5:
        parts.append("方向不符已降分")

    if not signals.get("impact", {}).get("has_quantified_impact", True):
        parts.append("项目描述中未找到量化指标")

    if not parts:
        return f"综合匹配 {total}/10"
    return f"综合 {total}/10：" + "；".join(parts[:6])


DIMENSION_LABELS_V1 = [
    ("skills", "技能匹配"),
    ("title", "职位方向"),
    ("experience", "工作经验"),
    ("location", "工作地点"),
    ("salary", "薪资期望"),
    ("education", "学历"),
    ("soft_skills", "软实力"),
]

DIMENSION_LABELS_V2 = [
    ("skills", "技能匹配"),
    ("experience", "工作经验"),
    ("role_match", "职位方向"),
    ("industry_match", "行业匹配"),
    ("education", "学历"),
    ("location", "工作地点"),
    ("salary", "薪资期望"),
    ("impact", "项目影响力"),
    ("soft_skills", "软实力"),
    ("growth_potential", "成长潜力"),
]


def extract_breakdown_for_api(score_breakdown: Optional[dict]) -> Optional[dict]:
    """将 score_breakdown 整理为前端友好的 breakdown 结构。"""
    if not score_breakdown:
        return None

    version = score_breakdown.get("version", 1)
    labels = DIMENSION_LABELS_V2 if version >= 2 else DIMENSION_LABELS_V1
    dimensions = []
    for key, label in labels:
        dim = score_breakdown.get(key)
        if not dim or not isinstance(dim, dict) or "weight" not in dim:
            continue
        weight = float(dim.get("weight") or 0)
        dimensions.append(
            {
                "key": key,
                "label": label,
                "score": dim.get("score"),
                "ratio": dim.get("ratio"),
                "weight": weight,
                "weight_pct": round(weight / 10.0 * 100),
            }
        )

    skills = score_breakdown.get("skills") or {}
    soft = score_breakdown.get("soft_skills") or {}
    if not isinstance(skills, dict):
        skills = {}
    if not isinstance(soft, dict):
        soft = {}
    return {
        "version": version,
        "dimensions": dimensions,
        "missing_skills": skills.get("missing") or [],
        "matched_skills": skills.get("matched") or [],
        "soft_skills_missing": soft.get("missing") or [],
    }

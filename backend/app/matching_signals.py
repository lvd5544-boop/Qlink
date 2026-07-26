"""
匹配补充信号层 — 参与总分或仅展示（不参与总分以避免偏见）。

参考 v2.0 设计：
  - 计入总分：impact, industry_match, growth_potential
  - 仅展示：education_prestige, stability, upskill_difficulty, interview/offer 概率
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .company_registry import normalize_skill_name

# 行业关键词簇
INDUSTRY_CLUSTERS: Dict[str, Set[str]] = {
    "fintech": {"金融", "银行", "证券", "支付", "fintech", "风控", "量化", "quant", "trading"},
    "saas": {"saas", "salesforce", "hubspot", "atlassian", "企业服务", "b2b"},
    "ecommerce": {"电商", "零售", "淘宝", "京东", "拼多多", "e-commerce"},
    "gaming": {"游戏", "game", "unity", "手游"},
    "ai": {"人工智能", "机器学习", "llm", "nlp", "deep learning", "ai"},
    "quant": {"量化", "quant", "对冲基金", "hedge fund", "prop trading", "做市"},
}

# 名校（仅展示，不计入总分）
PRESTIGE_SCHOOLS = {
    "cmu",
    "mit",
    "stanford",
    "berkeley",
    "caltech",
    "harvard",
    "清华",
    "北大",
    "复旦",
    "上交",
    "浙大",
    "中科大",
}

# 知名公司（行业匹配加分用）
PRESTIGE_COMPANIES = {
    "google",
    "meta",
    "amazon",
    "microsoft",
    "apple",
    "netflix",
    "腾讯",
    "阿里",
    "字节",
    "华为",
    "美团",
    "京东",
}

IMPACT_PATTERNS = [
    r"\d+\s*%",
    r"提升\s*\d+",
    r"降低\s*\d+",
    r"\d+\s*万\s*用户",
    r"\d+\s*million",
    r"节省\s*\d+",
    r"增长\s*\d+",
    r"qps\s*\d+",
    r"latency\s*\d+",
]

LEARNING_SIGNALS = [
    "开源",
    "github",
    "博客",
    "blog",
    "自学",
    "证书",
    "certification",
    "promotion",
    "晋升",
    "升职",
    "lead",
    "tech lead",
]

LEADERSHIP_SIGNALS = [
    "led a team",
    "managed",
    "mentored",
    "带领",
    "主导",
    "负责团队",
    "带团队",
]

COMMUNICATION_SIGNALS = [
    "cross-functional",
    "stakeholder",
    "client-facing",
    "跨部门",
    "协调",
    "汇报",
]

TREND_SKILLS_BY_ROLE: Dict[str, Set[str]] = {
    "ai": {"transformer", "rag", "llm", "fine-tuning", "pytorch", "langchain"},
    "quant": {"python", "c++", "pandas", "numpy", "backtest", "统计", "概率"},
    "engineering": {"kubernetes", "docker", "microservice", "redis", "kafka"},
    "data": {"spark", "sql", "dbt", "airflow", "tableau"},
}

# 技能补齐难度：已有技能 → 容易学的缺失技能
SKILL_PREREQUISITES: Dict[str, Set[str]] = {
    "kubernetes": {"docker"},
    "k8s": {"docker"},
    "spring boot": {"spring", "java"},
    "pytorch": {"python"},
    "tensorflow": {"python"},
    "深度学习": {"机器学习", "python"},
    "机器学习": {"python", "统计"},
}


def _resume_full_text(resume_json: dict) -> str:
    parts = [
        resume_json.get("summary") or "",
        resume_json.get("school") or "",
        resume_json.get("education") or "",
    ]
    for exp in resume_json.get("work_experience") or []:
        if isinstance(exp, dict):
            parts.extend(
                [
                    exp.get("company") or "",
                    exp.get("position") or "",
                    exp.get("description") or "",
                ]
            )
    return " ".join(parts).lower()


def _infer_industries(text: str) -> Set[str]:
    found: Set[str] = set()
    t = text.lower()
    for industry, kws in INDUSTRY_CLUSTERS.items():
        if any(kw.lower() in t for kw in kws):
            found.add(industry)
    return found


def _infer_job_industry(job_json: dict, job_title: str = "") -> Set[str]:
    skill_names = []
    for s in job_json.get("required_skills") or []:
        if isinstance(s, dict):
            skill_names.append(s.get("name") or "")
        else:
            skill_names.append(str(s))
    blob = " ".join(
        [
            job_title,
            job_json.get("title") or "",
            job_json.get("company_name") or "",
            " ".join(str(r) for r in job_json.get("responsibilities") or []),
            " ".join(skill_names),
        ]
    ).lower()
    return _infer_industries(blob)


def score_industry_match(
    resume_json: dict, job_json: dict, job_title: str = ""
) -> Tuple[float, dict]:
    """业务/行业匹配 0~1。"""
    resume_ind = _infer_industries(_resume_full_text(resume_json))
    job_ind = _infer_job_industry(job_json, job_title)

    if not job_ind:
        return 0.85, {"resume_industries": sorted(resume_ind), "job_industries": [], "overlap": []}

    overlap = resume_ind & job_ind
    if overlap:
        ratio = len(overlap) / len(job_ind)
        return min(0.5 + ratio * 0.5, 1.0), {
            "resume_industries": sorted(resume_ind),
            "job_industries": sorted(job_ind),
            "overlap": sorted(overlap),
        }

    # 无重叠但有相关大厂经历
    text = _resume_full_text(resume_json)
    if any(c in text for c in PRESTIGE_COMPANIES):
        return 0.45, {
            "resume_industries": sorted(resume_ind),
            "job_industries": sorted(job_ind),
            "overlap": [],
            "note": "行业不完全匹配，但有知名公司经历",
        }
    return 0.2, {
        "resume_industries": sorted(resume_ind),
        "job_industries": sorted(job_ind),
        "overlap": [],
    }


def score_impact(resume_json: dict) -> Tuple[float, dict]:
    """项目影响力 0~1：量化成果、数字指标。"""
    text = _resume_full_text(resume_json)
    if not text.strip():
        return 0.3, {"metrics_found": [], "has_quantified_impact": False}

    metrics: List[str] = []
    for pat in IMPACT_PATTERNS:
        for m in re.findall(pat, text, re.I):
            if m not in metrics:
                metrics.append(m)

    weak_only = "开发" in text or "负责" in text
    if not metrics:
        return 0.35 if weak_only else 0.25, {
            "metrics_found": [],
            "has_quantified_impact": False,
            "hint": "建议补充如「提升30%效率」「服务100万用户」等量化描述",
        }

    ratio = min(len(metrics) / 3.0, 1.0)
    return max(0.4, ratio), {
        "metrics_found": metrics[:8],
        "has_quantified_impact": True,
    }


def score_growth_potential(
    resume_json: dict, job_json: dict, job_title: str = ""
) -> Tuple[float, dict]:
    """成长潜力 0~1：学习能力 + 成长速度 + 技术趋势。"""
    text = _resume_full_text(resume_json)

    learning_hits = [s for s in LEARNING_SIGNALS if s.lower() in text]
    learning_ratio = min(len(learning_hits) / 3.0, 1.0)

    # 成长速度：年限 vs 职级
    total_years = sum(
        float(e.get("duration_years") or 0)
        for e in resume_json.get("work_experience") or []
        if isinstance(e, dict)
    )
    senior_keywords = {"lead", "tech lead", "经理", "主管", "senior", "架构"}
    positions = " ".join(
        (e.get("position") or "").lower()
        for e in resume_json.get("work_experience") or []
        if isinstance(e, dict)
    )
    is_senior = any(k in positions for k in senior_keywords)
    if total_years <= 3 and is_senior:
        growth_speed = 1.0
    elif total_years <= 5 and is_senior:
        growth_speed = 0.8
    else:
        growth_speed = 0.5

    # 技术趋势
    role_key = _detect_role_key(job_title or job_json.get("title") or "")
    trend_skills = TREND_SKILLS_BY_ROLE.get(role_key, TREND_SKILLS_BY_ROLE["engineering"])
    resume_skills = {
        normalize_skill_name(s.get("name", "") if isinstance(s, dict) else str(s))
        for s in resume_json.get("skills") or []
    }
    trend_hits = [t for t in trend_skills if any(t in rs or rs in t for rs in resume_skills)]
    trend_ratio = min(len(trend_hits) / max(len(trend_skills) * 0.4, 1), 1.0)

    combined = learning_ratio * 0.35 + growth_speed * 0.35 + trend_ratio * 0.30
    return round(combined, 3), {
        "learning_signals": learning_hits[:6],
        "growth_speed": round(growth_speed, 2),
        "trend_matched": trend_hits[:6],
        "role_key": role_key,
    }


def _detect_role_key(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ("quant", "量化", "交易员", "trading")):
        return "quant"
    if any(k in t for k in ("ai", "机器学习", "算法", "nlp", "llm")):
        return "ai"
    if any(k in t for k in ("数据", "data", "分析师")):
        return "data"
    return "engineering"


def score_education_prestige(resume_json: dict) -> Tuple[float, dict]:
    """学校背景 0~1，仅展示，不计入总分。"""
    school = (resume_json.get("school") or resume_json.get("education") or "").lower()
    tier = resume_json.get("school_tier") or ""
    hits = [s for s in PRESTIGE_SCHOOLS if s in school]
    if hits or tier in ("985", "211", "双一流"):
        return 0.9, {"prestige_schools": hits, "school_tier": tier, "display_only": True}
    if school:
        return 0.5, {"prestige_schools": [], "school_tier": tier, "display_only": True}
    return 0.0, {"prestige_schools": [], "school_tier": tier, "display_only": True}


def score_stability(resume_json: dict) -> Tuple[float, dict]:
    """跳槽稳定性 0~1，仅展示。"""
    exps = [e for e in resume_json.get("work_experience") or [] if isinstance(e, dict)]
    if not exps:
        return 0.7, {"avg_tenure_years": None, "short_stints": 0, "risk": "unknown"}

    tenures = [float(e.get("duration_years") or 0) for e in exps if e.get("duration_years")]
    if not tenures:
        return 0.7, {"avg_tenure_years": None, "short_stints": 0, "risk": "unknown"}

    avg = sum(tenures) / len(tenures)
    short = sum(1 for t in tenures if 0 < t < 1.0)
    if avg >= 2.0 and short == 0:
        return 1.0, {"avg_tenure_years": round(avg, 1), "short_stints": short, "risk": "low"}
    if avg >= 1.0 or short <= 1:
        return 0.65, {"avg_tenure_years": round(avg, 1), "short_stints": short, "risk": "medium"}
    return 0.35, {"avg_tenure_years": round(avg, 1), "short_stints": short, "risk": "high"}


def estimate_upskill_difficulty(
    missing_skills: List[str],
    known_skills: Set[str],
) -> dict:
    """补齐成本评估。"""
    easy: List[str] = []
    hard: List[str] = []

    for sk in missing_skills:
        prereqs = SKILL_PREREQUISITES.get(sk, set())
        if prereqs and prereqs & known_skills:
            easy.append(sk)
        elif sk in {"数学", "机器学习", "深度学习", "统计"}:
            hard.append(sk)
        elif any(p in known_skills for p in prereqs):
            easy.append(sk)
        else:
            hard.append(sk)

    if not missing_skills:
        level = "none"
    elif len(hard) > len(easy):
        level = "high"
    elif easy:
        level = "low"
    else:
        level = "medium"

    return {
        "level": level,
        "easy_to_learn": easy,
        "hard_to_learn": hard,
        "display_only": True,
    }


def estimate_probabilities(
    match_score: float,
    stability_ratio: float,
    impact_ratio: float,
) -> dict:
    """面试/Offer 概率启发式估算（0~100）。"""
    base = match_score * 8  # 0~80
    stability_bonus = stability_ratio * 10
    impact_bonus = impact_ratio * 10
    interview = min(int(base + stability_bonus * 0.5 + 10), 95)
    offer = min(int(interview * 0.45 + impact_bonus * 0.3), 90)
    return {
        "interview_probability": interview,
        "offer_probability": offer,
        "display_only": True,
        "note": "基于规则估算，非真实预测模型",
    }


def compute_supplementary_signals(
    resume_json: dict,
    job_json: dict,
    job_title: str = "",
    missing_skills: Optional[List[str]] = None,
    known_skills: Optional[Set[str]] = None,
) -> dict:
    """汇总所有补充信号。"""
    ind_ratio, ind_detail = score_industry_match(resume_json, job_json, job_title)
    impact_ratio, impact_detail = score_impact(resume_json)
    growth_ratio, growth_detail = score_growth_potential(resume_json, job_json, job_title)
    prestige_ratio, prestige_detail = score_education_prestige(resume_json)
    stability_ratio, stability_detail = score_stability(resume_json)

    upskill = estimate_upskill_difficulty(
        missing_skills or [],
        known_skills or set(),
    )
    probs = estimate_probabilities(
        match_score=0, stability_ratio=stability_ratio, impact_ratio=impact_ratio
    )

    return {
        "industry_match": {"ratio": ind_ratio, **ind_detail},
        "impact": {"ratio": impact_ratio, **impact_detail},
        "growth_potential": {"ratio": growth_ratio, **growth_detail},
        "education_prestige": {"ratio": prestige_ratio, **prestige_detail},
        "stability": {"ratio": stability_ratio, **stability_detail},
        "upskill_difficulty": upskill,
        "probabilities": probs,
    }

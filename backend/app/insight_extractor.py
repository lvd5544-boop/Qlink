"""从经验帖文本中提取结构化录用信号（规则 + 句子级校验，可复现）"""
import logging
from typing import List, Dict

from .company_registry import infer_role_family, normalize_skill_name
from .insight_text_processor import is_hiring_related
from .insight_nlp import (
    classify_post_type,
    extract_school_tiers_with_negation,
    extract_keywords_with_negation,
    match_companies_in_post,
    split_company_weight,
    infer_recruitment_type,
)
from .company_registry import SOFT_SKILL_KEYWORDS, LEADERSHIP_KEYWORDS

logger = logging.getLogger(__name__)

TECH_SKILL_PATTERNS = [
    "java", "python", "go", "golang", "c++", "react", "vue", "spring",
    "mysql", "redis", "kafka", "kubernetes", "k8s", "docker", "aws",
    "机器学习", "深度学习", "算法", "数据分析", "sql", "linux",
    "分布式", "微服务", "android", "ios", "flutter",
]


def _extract_skills(text: str) -> List[str]:
    found = []
    lower = text.lower()
    for sk in TECH_SKILL_PATTERNS:
        if sk in lower or sk in text:
            n = normalize_skill_name(sk)
            if n and n not in found:
                found.append(n)
    return found[:15]


def extract_insights_from_post(
    post: dict,
    companies: List,
) -> List[Dict]:
    title = post.get("title", "")
    body = post.get("body", "")
    full = f"{title}\n{body}"
    if not is_hiring_related(full):
        return []

    platform = post.get("platform", "unknown")
    base_weight = float(post.get("platform_weight", 1.0))
    post_type = classify_post_type(title, body)
    recruitment_type = infer_recruitment_type(title, body)

    company_matches = match_companies_in_post(
        full,
        companies,
        corpus_companies=post.get("corpus_companies"),
    )
    if not company_matches:
        return []

    role_family = infer_role_family(title + " " + body[:200])
    school_tiers = extract_school_tiers_with_negation(full)
    soft_skills = extract_keywords_with_negation(full, SOFT_SKILL_KEYWORDS)
    leadership = extract_keywords_with_negation(full, LEADERSHIP_KEYWORDS)
    skills = _extract_skills(full)

    degree = None
    for d in ["博士", "硕士", "研究生", "本科", "phd", "master", "bachelor"]:
        if d.lower() in full.lower():
            degree = d
            break

    school_tier = school_tiers[0] if school_tiers else None
    n_co = len(company_matches)
    extractions = []

    for c, match_conf in company_matches[:5]:
        confidence = 0.4 + match_conf * 0.35
        if post_type == "offer":
            confidence += 0.15
        elif post_type == "failure":
            confidence -= 0.1
        if len(skills) >= 2:
            confidence += 0.08
        if school_tier:
            confidence += 0.05
        confidence = min(max(confidence, 0.2), 0.95)

        weight = split_company_weight(base_weight * confidence, n_co)

        extractions.append({
            "company_id": c.id,
            "company_name_raw": c.name,
            "role_family": role_family,
            "school_tier": school_tier,
            "degree": degree,
            "skills": skills,
            "soft_skills": soft_skills,
            "leadership_signals": leadership,
            "platform": platform,
            "extraction_confidence": round(confidence, 3),
            "weight": round(weight, 3),
            "is_offer_story": post_type == "offer",
            "post_type": post_type,
            "recruitment_type": recruitment_type,
            "company_match_confidence": match_conf,
            "post_id": post.get("db_id"),
        })
    return extractions

"""经验帖 NLP 规则：否定识别、帖子分类、公司实体置信度、多公司权重分摊"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .company_registry import (
    SCHOOL_TIER_PATTERNS,
    match_company_by_name,
)
from .models_db import Company

# 短别名易误匹配，需结合招聘上下文
SHORT_ALIAS_MIN_CONFIDENCE = 0.55
HIRING_CONTEXT_WORDS = [
    "面试",
    "校招",
    "社招",
    "offer",
    "录用",
    "上岸",
    "入职",
    "岗位",
    "求职",
    "简历",
    "笔试",
    "复试",
    "hr",
    "背调",
    "实习",
    "转正",
    "hiring",
    "interview",
]

NEGATION_MARKERS = [
    "不是",
    "并非",
    "不限",
    "无要求",
    "不要求",
    "没有要求",
    "非必须",
    "不卡",
    "不唯",
    "无需",
    "未要求",
    "不看",
    "不限制",
]

FAILURE_SIGNALS = [
    "挂了",
    "被拒",
    "拒绝",
    "凉了",
    "挂了",
    "没进",
    "挂了",
    "reject",
    "rejected",
    "failed",
    "failure",
    "挂经",
    "挂掉",
    "一面挂",
    "二面挂",
    "三面挂",
]

OFFER_SIGNALS = ["offer", "录用", "上岸", "入职", "拿到", "accepted", "hired", "oc"]

CAMPUS_SIGNALS = ["校招", "应届", "毕业生", "campus", "new grad", "管培生"]
SOCIAL_SIGNALS = ["社招", "experienced", "跳槽", "在职", "年限"]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？!?\n；;]+", text or "")
    return [p.strip() for p in parts if p and len(p.strip()) >= 4]


def _sentence_has_negation(sentence: str) -> bool:
    return any(m in sentence for m in NEGATION_MARKERS)


def classify_post_type(title: str, body: str) -> str:
    """offer | failure | discussion"""
    full = f"{title}\n{body}".lower()
    if any(s in full for s in FAILURE_SIGNALS):
        return "failure"
    if any(s in full for s in OFFER_SIGNALS):
        return "offer"
    return "discussion"


def post_type_weight(post_type: str) -> float:
    return {"offer": 1.15, "discussion": 0.9, "failure": 0.35}.get(post_type, 0.85)


def infer_recruitment_type(title: str, body: str) -> str:
    full = f"{title}\n{body}".lower()
    if any(s in full for s in CAMPUS_SIGNALS):
        return "campus"
    if any(s in full for s in SOCIAL_SIGNALS):
        return "social"
    return "unknown"


def extract_school_tiers_with_negation(text: str) -> List[str]:
    """句子级提取院校层次，排除「不是 985 也能进」类否定句"""
    found: List[str] = []
    for sentence in _split_sentences(text):
        if _sentence_has_negation(sentence):
            continue
        for tier, patterns in SCHOOL_TIER_PATTERNS:
            for p in patterns:
                if p.lower() in sentence.lower() and tier not in found:
                    found.append(tier)
                    break
    return found


def _alias_confidence(candidate: str, canonical_name: str) -> float:
    cand = (candidate or "").strip()
    if not cand:
        return 0.0
    if cand == canonical_name:
        return 1.0
    if len(cand) <= 2:
        return 0.35
    if len(cand) <= 4 and all("\u4e00" <= ch <= "\u9fff" for ch in cand):
        return 0.5
    if len(cand) <= 5:
        return 0.65
    return 0.85


def _hiring_context_near(text: str, start: int, window: int = 48) -> bool:
    lo = max(0, start - window)
    hi = min(len(text), start + window)
    snippet = text[lo:hi]
    return any(w in snippet for w in HIRING_CONTEXT_WORDS)


def _find_mentions(text: str, candidate: str) -> List[int]:
    positions = []
    if not candidate:
        return positions
    if all(ord(ch) < 128 for ch in candidate):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            positions.append(m.start())
    else:
        start = 0
        while True:
            idx = text.find(candidate, start)
            if idx < 0:
                break
            positions.append(idx)
            start = idx + len(candidate)
    return positions


def match_companies_in_post(
    text: str,
    companies: List[Company],
    *,
    corpus_companies: Optional[List[str]] = None,
) -> List[Tuple[Company, float]]:
    """
    返回 [(公司, 匹配置信度)]，短别名需上下文；多公司由调用方分摊权重。
    """
    if not text:
        return []

    matched: List[Tuple[Company, float]] = []
    seen_ids = set()

    for name in corpus_companies or []:
        c = match_company_by_name(name, companies)
        if c and c.id not in seen_ids:
            seen_ids.add(c.id)
            matched.append((c, 0.95))

    for c in companies:
        if c.id in seen_ids:
            continue
        best_conf = 0.0
        for cand in [c.name] + list(c.name_aliases or []):
            if not cand or len(cand) < 2:
                continue
            positions = _find_mentions(text, cand)
            if not positions:
                continue
            conf = _alias_confidence(cand, c.name)
            if conf < SHORT_ALIAS_MIN_CONFIDENCE:
                if not any(_hiring_context_near(text, pos) for pos in positions):
                    continue
            best_conf = max(best_conf, conf)
        if best_conf > 0:
            seen_ids.add(c.id)
            matched.append((c, round(best_conf, 3)))

    matched.sort(key=lambda x: -x[1])
    return matched[:5]


def split_company_weight(base_weight: float, n_companies: int) -> float:
    if n_companies <= 0:
        return base_weight
    return base_weight / n_companies


def extract_keywords_with_negation(text: str, keyword_list: List[str]) -> List[str]:
    """句子级关键词，跳过含否定词的句子（如「不是 985 也能进」）。"""
    found: List[str] = []
    for sentence in _split_sentences(text):
        if _sentence_has_negation(sentence):
            continue
        for kw in keyword_list:
            if kw in sentence and kw not in found:
                found.append(kw)
    return found


def school_tier_disclaimer() -> str:
    return (
        "院校层次仅反映公开经验帖中的提及频率，不代表企业官方筛选标准，不建议作为唯一录用判断依据。"
    )

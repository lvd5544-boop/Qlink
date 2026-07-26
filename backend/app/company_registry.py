import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import Company

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).parent / "data" / "companies_seed.json"

SOFT_SKILL_KEYWORDS = [
    "沟通",
    "协作",
    "团队合作",
    "跨部门",
    "协调",
    "表达",
    "书面",
    "口头",
    "抗压",
    "责任心",
    "自驱",
    "主动",
    "学习能力",
    "适应",
    "细致",
    "严谨",
    "英语",
    "外语",
    "演讲",
    "汇报",
]

LEADERSHIP_KEYWORDS = [
    "领导",
    "带领",
    "带团队",
    "管理",
    "主导",
    "负责",
    "项目负责人",
    "项目经理",
    "mentor",
    "指导",
    "统筹",
    "决策",
]

COMMUNICATION_KEYWORDS = [
    "沟通",
    "协调",
    "汇报",
    "表达",
    "演讲",
    "书面",
    "跨部门",
    "客户沟通",
]

SCHOOL_TIER_PATTERNS = [
    ("985", ["985", "一流大学"]),
    ("211", ["211"]),
    ("双一流", ["双一流"]),
    ("硕士", ["硕士", "研究生", "master"]),
    ("博士", ["博士", "phd", "博士研究生"]),
    ("本科", ["本科", "学士", "统招本科"]),
]

ROLE_FAMILIES = {
    "engineering": [
        "工程师",
        "开发",
        "研发",
        "算法",
        "架构",
        "测试",
        "运维",
        "backend",
        "frontend",
    ],
    "product": ["产品", "产品经理", "pm"],
    "data": ["数据", "分析", "算法", "科学家"],
    "management": ["经理", "总监", "主管", "负责人", "管理"],
    "sales": ["销售", "商务", "市场", "客户", "客户经理", "营销", "政企"],
    "finance": ["财务", "会计", "审计", "金融"],
    "general": [],
}


def infer_role_family(title: str) -> str:
    if not title:
        return "general"
    t = title.lower()
    # 先匹配更具体的族，避免「客户经理」被「经理」误判为 management
    priority_order = ["sales", "finance", "product", "data", "engineering", "management"]
    for family in priority_order:
        for kw in ROLE_FAMILIES.get(family, []):
            if kw.lower() in t:
                return family
    return "general"


def extract_keywords_from_text(text: str, keyword_list: List[str]) -> List[str]:
    if not text:
        return []
    found = []
    for kw in keyword_list:
        if kw in text and kw not in found:
            found.append(kw)
    return found


def extract_school_tiers_from_text(text: str) -> List[str]:
    if not text:
        return []
    tiers = []
    for tier, patterns in SCHOOL_TIER_PATTERNS:
        for p in patterns:
            if p.lower() in text.lower() and tier not in tiers:
                tiers.append(tier)
    return tiers


def normalize_skill_name(name: str) -> str:
    return (name or "").strip().lower()


def increment_freq(freq: Dict[str, int], key: str, amount: int = 1):
    if not key:
        return
    freq[key] = freq.get(key, 0) + amount


def top_n_freq(freq: Dict[str, int], n: int = 15) -> Dict[str, int]:
    items = sorted(freq.items(), key=lambda x: -x[1])[:n]
    return dict(items)


TIER_LABELS = {
    "fortune500": "世界500强",
    "soe": "国有企业",
    "foreign": "外资企业",
    "hot": "热门民企",
    "other": "其他",
}


async def seed_companies(db: AsyncSession) -> int:
    if not SEED_PATH.exists():
        logger.warning("companies_seed.json not found")
        return 0
    with open(SEED_PATH, encoding="utf-8") as f:
        seeds = json.load(f)

    added = 0
    updated = 0
    for item in seeds:
        stmt = select(Company).where(Company.name == item["name"])
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            aliases = set(existing.name_aliases or [])
            aliases.update(item.get("aliases", []))
            existing.name_aliases = list(aliases)
            existing.tier = item.get("tier", existing.tier)
            existing.industry = item.get("industry", existing.industry)
            updated += 1
            continue
        company = Company(
            name=item["name"],
            name_aliases=item.get("aliases", []),
            tier=item.get("tier", "other"),
            industry=item.get("industry"),
        )
        db.add(company)
        added += 1
    await db.commit()
    logger.info("Companies seed: added=%s updated=%s", added, updated)
    return added


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def match_company_by_name(company_name: str, companies: List[Company]) -> Optional[Company]:
    if not company_name:
        return None
    name = company_name.strip()
    name_l = _norm(name)
    best = None
    best_len = 0
    for c in companies:
        candidates = [c.name] + list(c.name_aliases or [])
        for cand in candidates:
            if not cand:
                continue
            cand_l = _norm(cand)
            if cand_l == name_l:
                return c
            if cand_l in name_l or name_l in cand_l:
                if len(cand) > best_len:
                    best = c
                    best_len = len(cand)
    return best


def match_companies_in_text(text: str, companies: List[Company]) -> List[Company]:
    """在岗位描述/标题中识别公司（复用经验帖实体置信度规则）"""
    from .insight_nlp import match_companies_in_post

    return [c for c, _conf in match_companies_in_post(text, companies)]

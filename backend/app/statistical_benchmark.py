"""录用画像统计模型：加权频率 + 拉普拉斯平滑 + Wilson 置信区间"""

import math
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

from .insight_nlp import school_tier_disclaimer

logger = logging.getLogger(__name__)

MAX_USER_SUBMISSION_WEIGHT_SHARE = 0.12
LAPLACE_ALPHA = 1.0

# 样本量分级（建议阈值）
MIN_FORUM_SAMPLES_DISPLAY = 10
MIN_FORUM_SAMPLES_CREDIBLE = 30
MIN_FORUM_SAMPLES_STABLE = 100

# 兼容旧引用
MIN_FORUM_SAMPLES_FOR_BENCHMARK = MIN_FORUM_SAMPLES_DISPLAY

SOURCE_PLATFORM_CALIBRATION = {
    "corpus": 0.35,
    "hackernews": 0.9,
    "reddit": 1.0,
    "v2ex": 1.0,
    "unknown": 0.8,
}

POST_TYPE_CALIBRATION = {
    "offer": 1.15,
    "discussion": 0.9,
    "failure": 0.35,
}


def resolve_sample_tier(n_posts: int, *, n_live: Optional[int] = None) -> str:
    """样本等级仅按非语料（真实网络帖）计数。"""
    effective = n_live if n_live is not None else n_posts
    if effective >= MIN_FORUM_SAMPLES_STABLE:
        return "stable"
    if effective >= MIN_FORUM_SAMPLES_CREDIBLE:
        return "credible"
    if effective >= MIN_FORUM_SAMPLES_DISPLAY:
        return "exploratory"
    return "insufficient"


def sample_tier_label(tier: str) -> str:
    return {
        "stable": "样本较充足（100+ 帖）",
        "credible": "样本较可信（30+ 帖）",
        "exploratory": "探索性结论（10–29 帖）",
        "insufficient": "样本不足（<10 帖）",
    }.get(tier, tier)


def wilson_interval(successes: float, n: float, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def weighted_category_distribution(
    items: List[Tuple[str, float]],
    alpha: float = LAPLACE_ALPHA,
) -> Dict[str, Dict[str, Any]]:
    totals: Dict[str, float] = defaultdict(float)
    for cat, w in items:
        if not cat:
            continue
        totals[cat] += w
    n_eff = sum(totals.values())
    if n_eff <= 0:
        return {}

    categories = list(totals.keys())
    vocab_size = max(len(categories), 1)
    dist = {}
    for cat in categories:
        count = totals[cat]
        smoothed = (count + alpha) / (n_eff + alpha * vocab_size)
        low, high = wilson_interval(count, max(n_eff, 1))
        dist[cat] = {
            "weight": round(count, 2),
            "prob": round(smoothed, 4),
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
        }
    return dist


def aggregate_extractions_to_bucket(extractions: List[dict]) -> dict:
    bucket = {
        "n_posts": 0,
        "n_effective": 0.0,
        "source_breakdown": defaultdict(float),
        "school_items": [],
        "skill_items": [],
        "soft_items": [],
        "leadership_items": [],
        "degree_items": [],
        "post_types": defaultdict(int),
        "recruitment_types": defaultdict(int),
    }
    seen_posts = set()
    seen_live = set()
    seen_corpus = set()
    for ex in extractions:
        pid = ex.get("post_id")
        plat = ex.get("platform") or "unknown"
        if pid and pid not in seen_posts:
            seen_posts.add(pid)
            bucket["n_posts"] += 1
            if plat == "corpus":
                seen_corpus.add(pid)
            else:
                seen_live.add(pid)
        w = float(ex.get("weight") or 0.5)
        w *= SOURCE_PLATFORM_CALIBRATION.get(plat, 0.8)
        post_type = ex.get("post_type") or "discussion"
        w *= POST_TYPE_CALIBRATION.get(post_type, 0.9)
        bucket["post_types"][post_type] += 1
        rec_type = ex.get("recruitment_type") or "unknown"
        bucket["recruitment_types"][rec_type] += 1

        bucket["n_effective"] += w
        bucket["source_breakdown"][plat] += w

        if ex.get("school_tier") and post_type != "failure":
            bucket["school_items"].append((ex["school_tier"], w))
        if ex.get("degree"):
            bucket["degree_items"].append((ex["degree"], w))
        for sk in ex.get("skills") or []:
            bucket["skill_items"].append((sk, w))
        for ss in ex.get("soft_skills") or []:
            bucket["soft_items"].append((ss, w))
        for le in ex.get("leadership_signals") or []:
            bucket["leadership_items"].append((le, w))

    bucket["n_posts_live"] = len(seen_live)
    bucket["n_posts_corpus"] = len(seen_corpus)
    return bucket


def dist_to_simple_freq(dist: Dict[str, Dict]) -> Dict[str, int]:
    return {k: max(1, int(round(v.get("weight", 0)))) for k, v in dist.items()}


def generate_statistical_conclusions(
    school_dist: Dict,
    skill_dist: Dict,
    soft_dist: Dict,
    leadership_dist: Dict,
    n_posts: int,
    source_breakdown: Dict,
    sample_tier: str,
) -> List[str]:
    conclusions = []
    tier_label = sample_tier_label(sample_tier)

    if sample_tier == "insufficient":
        conclusions.append(
            f"网络经验帖有效样本仅 {n_posts} 条，未达到展示阈值（{MIN_FORUM_SAMPLES_DISPLAY} 帖），"
            "暂不输出录用画像统计，请同步更多公开经验数据。"
        )
        return conclusions

    conclusions.append(f"样本等级：{tier_label}（当前 {n_posts} 条去重帖）。")
    if sample_tier == "exploratory":
        conclusions.append(
            f"样本量在 {MIN_FORUM_SAMPLES_DISPLAY}–{MIN_FORUM_SAMPLES_CREDIBLE - 1} 之间，"
            "结论仅供探索参考，建议达到 30+ 帖后再作重要决策。"
        )

    def top_lines(dist: Dict, label: str, min_prob: float = 0.12):
        ranked = sorted(dist.items(), key=lambda x: -x[1].get("prob", 0))[:4]
        for name, stats in ranked:
            p = stats.get("prob", 0)
            if p < min_prob:
                continue
            ci_l = stats.get("ci_low", 0) * 100
            ci_h = stats.get("ci_high", 0) * 100
            prefix = "在公开经验帖中提及较多" if label == "院校层次" else "信号出现频率较高"
            conclusions.append(
                f"【{label}】{name}：{prefix}，加权估计约 {p * 100:.1f}%（近似区间 {ci_l:.0f}%–{ci_h:.0f}%）"
            )

    top_lines(school_dist, "院校层次")
    top_lines(skill_dist, "技能", 0.10)
    top_lines(soft_dist, "软实力")
    top_lines(leadership_dist, "领导力信号", 0.08)

    conclusions.append(school_tier_disclaimer())

    if source_breakdown:
        parts = [f"{k}({int(v)})" for k, v in sorted(source_breakdown.items(), key=lambda x: -x[1])]
        conclusions.append(f"数据来源构成（加权）：{', '.join(parts)}")

    conclusions.append(
        f"统计方法：拉普拉斯平滑 + Wilson 区间；已按帖子类型（offer/讨论/失败）与来源平台校准权重。"
    )
    return conclusions


def compute_confidence_score(n_posts: int, n_effective: float, num_metrics: int) -> float:
    tier = resolve_sample_tier(n_posts)
    if tier == "insufficient":
        return round(min(0.25, 0.05 + n_posts * 0.02), 2)
    if tier == "exploratory":
        base = 0.38 + min(n_posts, 29) * 0.012
    elif tier == "credible":
        base = 0.55 + min(n_posts - 30, 70) * 0.004
    else:
        base = 0.72 + min(n_posts - 100, 200) * 0.001
    base += min(n_effective, 50) * 0.004 + min(num_metrics, 4) * 0.02
    return round(min(base, 0.95), 2)


def build_statistical_benchmark_payload(bucket: dict) -> dict:
    school_dist = weighted_category_distribution(bucket["school_items"])
    skill_dist = weighted_category_distribution(bucket["skill_items"])
    soft_dist = weighted_category_distribution(bucket["soft_items"])
    leadership_dist = weighted_category_distribution(bucket["leadership_items"])
    degree_dist = weighted_category_distribution(bucket["degree_items"])

    source_breakdown = dict(bucket["source_breakdown"])
    n_posts = bucket["n_posts"]
    n_live = bucket.get("n_posts_live", n_posts)
    n_corpus = bucket.get("n_posts_corpus", 0)
    sample_tier = resolve_sample_tier(n_posts, n_live=n_live)
    conclusions = generate_statistical_conclusions(
        school_dist, skill_dist, soft_dist, leadership_dist, n_live, source_breakdown, sample_tier
    )
    if n_corpus > 0 and sample_tier == "insufficient":
        conclusions.append(
            f"另有 {n_corpus} 条本地演示语料未计入样本等级（语料仅供界面预览，不作统计依据）。"
        )
    elif n_corpus > 0 and n_live >= MIN_FORUM_SAMPLES_DISPLAY:
        corpus_share = source_breakdown.get("corpus", 0) / max(bucket["n_effective"], 0.01)
        if corpus_share > 0.4:
            conclusions.append("网络样本中演示语料占比较高，结论请优先参考非语料来源。")
    confidence = compute_confidence_score(
        n_live, bucket["n_effective"], len(school_dist) + len(skill_dist)
    )

    return {
        "school_tier_dist": dist_to_simple_freq(school_dist),
        "skill_freq": dist_to_simple_freq(skill_dist),
        "soft_skill_freq": dist_to_simple_freq(soft_dist),
        "leadership_freq": dist_to_simple_freq(leadership_dist),
        "degree_freq": dist_to_simple_freq(degree_dist),
        "statistical_detail": {
            "school_tier": school_dist,
            "skills": skill_dist,
            "soft_skills": soft_dist,
            "leadership": leadership_dist,
            "degree": degree_dist,
            "sample_tier": sample_tier,
            "n_samples_live": n_live,
            "n_samples_corpus": n_corpus,
            "post_types": dict(bucket.get("post_types") or {}),
            "recruitment_types": dict(bucket.get("recruitment_types") or {}),
        },
        "statistical_conclusions": conclusions,
        "source_breakdown": source_breakdown,
        "confidence_score": confidence,
        "n_samples": n_posts,
        "n_samples_live": n_live,
        "n_samples_corpus": n_corpus,
        "n_effective_weight": round(bucket["n_effective"], 2),
        "sample_tier": sample_tier,
        "methodology": (
            "录用画像来自公开可访问的网络经验帖与整理语料（不爬登录态、不绕过验证码），"
            "经句子级否定过滤、帖子类型分类、公司实体置信匹配后，"
            "使用加权频率（Laplace 平滑）与 Wilson 区间估计；"
            f"展示阈值 {MIN_FORUM_SAMPLES_DISPLAY} 帖，较可信 {MIN_FORUM_SAMPLES_CREDIBLE} 帖，"
            f"较稳定 {MIN_FORUM_SAMPLES_STABLE}+ 帖；用户提交需审核且权重上限 "
            f"{int(MAX_USER_SUBMISSION_WEIGHT_SHARE * 100)}%。"
        ),
    }

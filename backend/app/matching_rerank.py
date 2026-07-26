"""
Layer 3: Top-K LLM 重排 — 在 hybrid 分数基础上微调 ±1.5 并生成深度理由。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_ADJUSTMENT = 1.5


def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _profile_summary(profile: dict) -> str:
    skills = []
    for s in profile.get("skills") or []:
        if isinstance(s, dict):
            skills.append(s.get("name", ""))
        else:
            skills.append(str(s))
    exps = []
    for e in profile.get("work_experience") or []:
        if isinstance(e, dict):
            exps.append(
                f"{e.get('company', '')}-{e.get('position', '')}({e.get('duration_years', 0)}年)"
            )
    return json.dumps(
        {
            "name": profile.get("name"),
            "expected_title": profile.get("expected_job_title"),
            "skills": skills[:15],
            "experience": exps[:5],
            "education": profile.get("education"),
            "summary": (profile.get("summary") or "")[:300],
        },
        ensure_ascii=False,
    )


def _job_summary(job_info: dict, job_title: str) -> str:
    skills = []
    for s in job_info.get("required_skills") or []:
        if isinstance(s, dict):
            skills.append(s.get("name", ""))
        else:
            skills.append(str(s))
    return json.dumps(
        {
            "title": job_title or job_info.get("title"),
            "required_skills": skills[:15],
            "experience_years": job_info.get("experience_years"),
            "location": job_info.get("location"),
            "salary": job_info.get("salary_range"),
            "responsibilities": (job_info.get("responsibilities") or [])[:5],
        },
        ensure_ascii=False,
    )


def _breakdown_summary(breakdown: dict) -> str:
    if not breakdown:
        return "{}"
    slim = {}
    for key in (
        "skills",
        "experience",
        "role_match",
        "industry_match",
        "education",
        "location",
        "salary",
        "impact",
        "soft_skills",
        "growth_potential",
    ):
        dim = breakdown.get(key)
        if dim:
            slim[key] = {
                "ratio": dim.get("ratio"),
                "score": dim.get("score"),
                "missing": dim.get("missing"),
                "matched": dim.get("matched"),
            }
    slim["potential_score"] = breakdown.get("potential_score")
    slim["improvement_delta"] = breakdown.get("improvement_delta")
    return json.dumps(slim, ensure_ascii=False)


async def llm_rerank_match(
    candidate_profile: dict,
    job_info: dict,
    job_title: str,
    hybrid_score: float,
    breakdown: dict,
) -> Tuple[float, str, Dict]:
    """
    LLM 重排：在 hybrid_score 基础上调整 ±1.5，返回 (final_score, reason, llm_meta)。
    无 API Key 或调用失败时回退 hybrid 理由。
    """
    from .llm_client import async_chat_completion, model_api_key
    from .matching_hybrid import build_match_reason_v2

    fallback_reason = build_match_reason_v2(breakdown, hybrid_score)
    if not model_api_key():
        return hybrid_score, fallback_reason, {"source": "hybrid_fallback", "llm_skipped": True}

    prompt = f"""你是专业招聘匹配评估专家。已有一套规则引擎给出 hybrid 评分，请你结合候选人画像与岗位 JD 做最终解读。

规则：
1. 最终 score 必须在 [{hybrid_score - MAX_ADJUSTMENT:.1f}, {hybrid_score + MAX_ADJUSTMENT:.1f}] 区间内
2. 若候选人期望职位与岗位职位大类明显不符（如开发 vs 销售/客户经理），adjustment 必须为负数，不得因技能重叠而抬高分数
3. reason 用 2~4 句中文，具体说明匹配点与主要差距，不要写「快速评估」
4. 只输出 JSON，格式：{{"score": 7.5, "reason": "...", "adjustment": 0.3}}

hybrid_score: {hybrid_score}
breakdown: {_breakdown_summary(breakdown)}
候选人: {_profile_summary(candidate_profile)}
岗位: {_job_summary(job_info, job_title)}
"""

    try:
        response = await async_chat_completion(
            messages=[
                {"role": "system", "content": "你只输出合法 JSON，不要 markdown。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        adjustment = float(result.get("adjustment", 0))
        adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))
        score = round(min(max(hybrid_score + adjustment, 0), 10), 1)
        reason = str(result.get("reason") or fallback_reason)
        return (
            score,
            reason,
            {
                "source": "llm_rerank",
                "hybrid_score": hybrid_score,
                "adjustment": adjustment,
                "llm_skipped": False,
            },
        )
    except Exception as e:
        logger.error("LLM rerank failed: %s", e)
        return hybrid_score, fallback_reason, {"source": "hybrid_fallback", "llm_error": str(e)}

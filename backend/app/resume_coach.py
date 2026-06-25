import json
import os
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .company_registry import infer_role_family, normalize_skill_name
from .insight_nlp import school_tier_disclaimer
from .market_analytics import get_company_profile

logger = logging.getLogger(__name__)


def get_openai_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def get_model():
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _resume_skill_set(resume_json: dict) -> set:
    skills = set()
    for s in resume_json.get("skills") or []:
        if isinstance(s, dict):
            skills.add(normalize_skill_name(s.get("name", "")))
        else:
            skills.add(normalize_skill_name(str(s)))
    return {s for s in skills if s}


def _freq_keys(freq: dict) -> List[str]:
    return list((freq or {}).keys())


def compute_gap_analysis(resume_json: dict, jd_insight: dict, hired_benchmark: dict) -> dict:
    """规则层差距分析，供 LLM 与前端展示"""
    use_stat = hired_benchmark.get("source") in ("statistical_forum", "demo_preview")
    resume_skills = _resume_skill_set(resume_json)
    if use_stat:
        target_skills = set(_freq_keys(hired_benchmark.get("skill_freq")))
        target_soft = set(_freq_keys(hired_benchmark.get("soft_skill_freq")))
        target_leadership = set(_freq_keys(hired_benchmark.get("leadership_freq")))
    else:
        target_skills = set()
        target_soft = set()
        target_leadership = set()

    resume_soft = set(resume_json.get("soft_skills") or [])
    resume_text = " ".join(
        [
            resume_json.get("summary") or "",
            resume_json.get("education") or "",
            " ".join(
                (exp.get("description") or "") if isinstance(exp, dict) else ""
                for exp in resume_json.get("work_experience") or []
            ),
        ]
    ).lower()

    soft_missing = [s for s in target_soft if s not in resume_soft and s not in resume_text]
    leadership_missing = [s for s in target_leadership if s not in resume_text]
    skills_missing = [s for s in target_skills if s not in resume_skills][:12]

    school_tiers = _freq_keys(hired_benchmark.get("school_tier_dist")) if use_stat else []
    user_tier = resume_json.get("school_tier") or ""
    education_gap = None
    if school_tiers and not user_tier:
        education_gap = (
            f"公开经验帖中较常提及的院校层次包括：{', '.join(school_tiers[:4])}。"
            f"{school_tier_disclaimer()}建议在学历栏写清院校与层次。"
        )
    elif hired_benchmark.get("source") == "demo_preview":
        education_gap = (
            "录用画像仅含演示语料，不能代表真实筛选标准；请优先参考左侧 JD 并同步公开经验帖。"
        )
    elif not use_stat and hired_benchmark.get("source") == "insufficient_forum":
        education_gap = "录用画像网络样本不足，请优先参考左侧 JD 偏好并同步公开经验数据"

    return {
        "skills_missing": skills_missing,
        "soft_skills_missing": soft_missing[:10],
        "leadership_signals_missing": leadership_missing[:8],
        "education_gap": education_gap,
        "skills_matched": list(resume_skills & target_skills)[:10],
    }


async def generate_resume_coach(
    db,
    resume_json: dict,
    company_id: str,
    role_family: Optional[str] = None,
    target_job_title: Optional[str] = None,
) -> Dict[str, Any]:
    profile = await get_company_profile(db, company_id, role_family)
    if not profile:
        raise ValueError("公司不存在")

    role_family = role_family or infer_role_family(
        target_job_title or resume_json.get("expected_job_title") or ""
    )

    jd_insight = next(
        (i for i in profile["jd_insights"] if i["role_family"] == role_family),
        profile["jd_insights"][0] if profile["jd_insights"] else {},
    )
    hired_benchmark = next(
        (b for b in profile["hired_benchmarks"] if b["role_family"] == role_family),
        profile["hired_benchmarks"][0] if profile["hired_benchmarks"] else {},
    )

    gaps = compute_gap_analysis(resume_json, jd_insight, hired_benchmark)

    company_name = profile["company"]["name"]
    benchmark_note = hired_benchmark.get("notes") or ""
    benchmark_source = hired_benchmark.get("source") or "statistical_forum"
    stat_conclusions = (hired_benchmark.get("statistical_summary") or {}).get("conclusions") or []
    methodology = hired_benchmark.get("methodology") or ""
    confidence = hired_benchmark.get("confidence_score")
    sample_tier = hired_benchmark.get("sample_tier") or (
        (hired_benchmark.get("statistical_summary") or {}).get("sample_tier")
    )

    prompt = f"""你是资深职业规划师。请根据以下信息，为求职者提供可执行的简历修改建议（中文）。

【写作原则 — 必须遵守】
1. 不要建议编造或夸大软实力/领导力；应指导用户在已有经历中补强证据。
2. 把已有项目中的协调、推动、复盘、影响人数写清楚；用数据证明沟通与协作。
3. 将模糊表述改为结果导向（指标、范围、前后对比）。
4. 关于院校层次：只能说「公开样本中出现频率」「经验帖中提及较多」；禁止说「该公司只要985」「不是211就没机会」等歧视性或绝对化表述。
5. {school_tier_disclaimer()}

目标公司：{company_name}
目标岗位方向：{role_family}
意向职位：{target_job_title or resume_json.get('expected_job_title') or '未指定'}

【公开招聘偏好（JD 聚合）】
技能词频：{json.dumps(jd_insight.get('skill_freq', {}), ensure_ascii=False)}
学历要求分布：{json.dumps(jd_insight.get('education_freq', {}), ensure_ascii=False)}
软实力词频：{json.dumps(jd_insight.get('soft_skill_freq', {}), ensure_ascii=False)}

【录用画像（统计模型，来源：{benchmark_source}，样本等级：{sample_tier}，置信度：{confidence}，网络帖样本：{hired_benchmark.get('n_samples', 0)}）】
{methodology}
统计结论：{json.dumps(stat_conclusions, ensure_ascii=False)}
{benchmark_note}
学校层次分布（仅供参考，非官方标准）：{json.dumps(hired_benchmark.get('school_tier_dist', {}), ensure_ascii=False)}
录用技能词频：{json.dumps(hired_benchmark.get('skill_freq', {}), ensure_ascii=False)}
录用软实力：{json.dumps(hired_benchmark.get('soft_skill_freq', {}), ensure_ascii=False)}
领导力相关：{json.dumps(hired_benchmark.get('leadership_freq', {}), ensure_ascii=False)}

【求职者当前简历摘要】
{json.dumps(resume_json, ensure_ascii=False)[:6000]}

【系统已识别的差距】
{json.dumps(gaps, ensure_ascii=False)}

请严格输出 JSON，格式如下：
{{
  "summary": "一段总体评价",
  "priority_actions": ["优先行动1", "优先行动2"],
  "suggestions": [
    {{
      "section": "工作经历|项目经历|技能|教育背景|自我评价",
      "field_path": "必填，如 work_experience[0].description、projects[0].description、summary、skills、basic.school",
      "priority": "高|中|低",
      "issue": "问题描述",
      "advice": "具体修改建议（强调用已有经历补强证据，而非空喊软实力）",
      "example_before": "必填，改写前的原句（从简历中摘录）",
      "example_after": "必填，改写后的示例句（含量化指标）"
    }}
  ],
  "school_advice": "院校与学历相关建议（遵守上述院校表述规范）或null",
  "soft_skill_advice": "软实力建议（写清项目中的协调、数据、影响范围，勿建议造假）"
}}
"""

    client = get_openai_client()
    model = get_model()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你只输出合法 JSON，不要 markdown 代码块。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or "{}"
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        coach = json.loads(content)
    except Exception as e:
        logger.warning("LLM resume coach failed: %s", e)
        coach = {
            "summary": "已根据岗位与录用画像完成规则分析，AI 详细建议暂时不可用，请稍后重试。",
            "priority_actions": [
                "在项目中补充协调范围、推动结果与量化指标",
                "将目标岗位高频技能用项目经历佐证",
            ][:2],
            "suggestions": [
                {
                    "section": "工作经历",
                    "field_path": "work_experience[0].description",
                    "priority": "高",
                    "issue": "经历描述偏笼统，缺少可验证的结果",
                    "advice": "为每个项目补充：你推动了什么、协调了谁、最终指标变化多少",
                    "example_before": "负责后端开发与维护",
                    "example_after": "负责订单模块开发，通过缓存优化将接口 P99 延迟降低 35%，日订单处理量达 8 万+",
                }
            ],
            "school_advice": gaps.get("education_gap"),
            "soft_skill_advice": (
                "不要空写「沟通能力强」；改为「跨 3 部门推进 XX，周期缩短 20%」等证据句。"
            ),
        }

    return {
        "company": profile["company"],
        "role_family": role_family,
        "gaps": gaps,
        "jd_insight": jd_insight,
        "hired_benchmark": {
            "source": benchmark_source,
            "n_samples": hired_benchmark.get("n_samples", 0),
            "confidence_score": confidence,
            "sample_tier": sample_tier,
            "methodology": methodology,
            "statistical_conclusions": stat_conclusions,
            "notes": benchmark_note,
            "school_tier_dist": hired_benchmark.get("school_tier_dist", {}),
            "skill_freq": hired_benchmark.get("skill_freq", {}),
            "soft_skill_freq": hired_benchmark.get("soft_skill_freq", {}),
            "leadership_freq": hired_benchmark.get("leadership_freq", {}),
        },
        "coach": coach,
    }

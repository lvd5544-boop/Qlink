import json
import os
import logging
from typing import Any, Dict, List, Optional

from .company_registry import infer_role_family, normalize_skill_name
from .insight_nlp import school_tier_disclaimer
from .llm_client import default_model_name
from .market_analytics import get_company_profile
from .provider_costs import extract_provider_usage
from .ai.data_sources import is_forum_layer_e

logger = logging.getLogger(__name__)


def _polish_existing_sentence(text: str) -> str:
    """Make an existing fact easier to read without adding a new fact."""
    cleaned = " ".join(str(text or "").split()).strip("；;。 ")
    if not cleaned:
        return ""
    if cleaned.startswith(("负责", "参与", "主导", "协助", "完成", "推动")):
        return f"{cleaned}。"
    return f"主要工作包括：{cleaned}。"


def build_rule_based_rewrite_suggestions(resume_json: dict) -> list[dict]:
    """Return faithful before/after examples when the model is unavailable.

    These examples only reorganize text already present in the resume. They do
    not insert metrics, skills, scope or outcomes that the candidate did not
    provide.
    """
    suggestions: list[dict] = []
    summary = str(resume_json.get("summary") or "").strip()
    if summary:
        after = _polish_existing_sentence(summary)
        if after and after != summary:
            suggestions.append(
                {
                    "section": "个人简介",
                    "field_path": "summary",
                    "priority": "中",
                    "issue": "个人简介可以改成更完整、顺畅的一句话。",
                    "advice": "这版只整理你已经写下的内容；如需进一步增强，请补充真实的职责范围和结果。",
                    "example_before": summary,
                    "example_after": after,
                }
            )

    section_specs = (
        ("工作经历", "work_experience", "company"),
        ("项目经历", "projects", "name"),
    )
    for section_label, section_key, name_key in section_specs:
        for index, item in enumerate(resume_json.get(section_key) or []):
            if not isinstance(item, dict):
                continue
            before = str(item.get("description") or "").strip()
            after = _polish_existing_sentence(before)
            if not before or not after or after == before:
                continue
            item_name = str(item.get(name_key) or f"第 {index + 1} 条").strip()
            suggestions.append(
                {
                    "section": section_label,
                    "field_path": f"{section_key}[{index}].description",
                    "priority": "中",
                    "issue": f"「{item_name}」的描述读起来不够完整。",
                    "advice": "先把原有事实整理成完整句；如果有真实数据或成果，可通过证据追问后再补充。",
                    "example_before": before,
                    "example_after": after,
                }
            )
            if len(suggestions) >= 3:
                return suggestions
    return suggestions


def get_model():
    return default_model_name("advisor_answer")


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
    """Gap vs employer JD insight. Forum/demo benchmarks are layer E qualitative only."""
    forum_layer_e = is_forum_layer_e(hired_benchmark.get("source"))
    resume_skills = _resume_skill_set(resume_json)
    # Formal skill targets come from JD insight only — never forum statistical profiles.
    target_skills = set(_freq_keys(jd_insight.get("skill_freq")))
    target_soft = set(_freq_keys(jd_insight.get("soft_skill_freq")))
    target_leadership = set(_freq_keys(jd_insight.get("leadership_freq")))

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

    education_gap = None
    if forum_layer_e:
        education_gap = (
            "网络论坛统计属于 E 层定性线索，不能作为企业录用画像或正式筛选标准；"
            "请优先参考企业 JD 与已确认岗位要求。"
        )
    elif hired_benchmark.get("source") == "insufficient_forum":
        education_gap = "录用画像网络样本不足，请优先参考左侧 JD 偏好"

    return {
        "skills_missing": skills_missing,
        "soft_skills_missing": soft_missing[:10],
        "leadership_signals_missing": leadership_missing[:8],
        "education_gap": education_gap,
        "skills_matched": list(resume_skills & target_skills)[:10],
        "forum_layer": "E" if forum_layer_e else None,
        "forum_qualitative_only": forum_layer_e,
    }


def _build_battle_card(
    resume_json: dict,
    company_name: str,
    role_family: str,
    target_job_title: Optional[str],
    gaps: dict,
    jd_insight: dict,
    hired_benchmark: dict,
    coach: dict,
) -> dict:
    """构建投递作战卡。"""
    jd_skills = list((jd_insight.get("skill_freq") or {}).keys())[:8]
    matched = gaps.get("skills_matched") or []
    missing = gaps.get("skills_missing") or []

    experience_to_strengthen = []
    for sug in (coach.get("suggestions") or [])[:4]:
        if sug.get("advice"):
            experience_to_strengthen.append(sug["advice"])

    do_not_fake = list(missing[:5])
    if gaps.get("soft_skills_missing"):
        do_not_fake.append(
            f"软实力「{'、'.join(gaps['soft_skills_missing'][:3])}」：如果没有真实经历，不建议硬写"
        )

    interview_questions = []
    for sug in (coach.get("suggestions") or [])[:3]:
        if sug.get("issue"):
            interview_questions.append(f"关于「{sug['issue']}」，请具体说明您的角色与可验证结果。")
    stat_conclusions = (hired_benchmark.get("statistical_summary") or {}).get("conclusions") or []
    for line in stat_conclusions[:2]:
        interview_questions.append(f"结合目标企业特点：{line}")

    evidence_to_prepare = [
        "项目复盘截图或文档",
        "可量化的业务/性能指标",
        "跨部门协作或推动成果的具体案例",
    ]
    if missing:
        evidence_to_prepare.append(f"与 {missing[0]} 相关的项目代码/方案文档")

    positioning = (
        f"面向 {company_name} {target_job_title or role_family} 方向，"
        f"已匹配 {len(matched)} 项核心能力，建议重点补强 {len(missing)} 项差距信号。"
    )

    resume_focus = (coach.get("priority_actions") or [])[:5]
    if not resume_focus:
        resume_focus = ["在已有项目中补充量化结果与角色边界", "用证据句替代空泛软实力表述"]

    return {
        "positioning": positioning,
        "resume_focus": resume_focus,
        "matched_signals": matched,
        "missing_signals": missing,
        "experience_to_strengthen": experience_to_strengthen
        or [
            "将模糊职责改为「动作 + 范围 + 结果」结构",
            "补充协调人数、影响范围、指标变化",
        ],
        "do_not_fake": do_not_fake or ["如果没有真实经历，不建议硬写"],
        "interview_questions": interview_questions[:6]
        or [
            "请具体说明您在项目中的角色边界与个人贡献。",
            "关键指标的基线和统计周期是什么？",
        ],
        "evidence_to_prepare": evidence_to_prepare,
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
意向职位：{target_job_title or resume_json.get("expected_job_title") or "未指定"}

【公开招聘偏好（JD 聚合）】
技能词频：{json.dumps(jd_insight.get("skill_freq", {}), ensure_ascii=False)}
学历要求分布：{json.dumps(jd_insight.get("education_freq", {}), ensure_ascii=False)}
软实力词频：{json.dumps(jd_insight.get("soft_skill_freq", {}), ensure_ascii=False)}

【录用画像（统计模型，来源：{benchmark_source}，样本等级：{sample_tier}，置信度：{confidence}，网络帖样本：{hired_benchmark.get("n_samples", 0)}）】
{methodology}
统计结论：{json.dumps(stat_conclusions, ensure_ascii=False)}
{benchmark_note}
学校层次分布（仅供参考，非官方标准）：{json.dumps(hired_benchmark.get("school_tier_dist", {}), ensure_ascii=False)}
录用技能词频：{json.dumps(hired_benchmark.get("skill_freq", {}), ensure_ascii=False)}
录用软实力：{json.dumps(hired_benchmark.get("soft_skill_freq", {}), ensure_ascii=False)}
领导力相关：{json.dumps(hired_benchmark.get("leadership_freq", {}), ensure_ascii=False)}

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

    model = get_model()
    metering = {
        "model_called": False,
        "provider_status": None,
        "provider_usage": None,
        "model_output_used": False,
    }
    coach = None
    from .llm_client import async_chat_completion, model_api_key

    if model_api_key():
        try:
            metering["model_called"] = True
            response = await async_chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "你只输出合法 JSON，不要 markdown 代码块。",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.3,
            )
            metering["provider_status"] = "succeeded"
            metering["provider_usage"] = extract_provider_usage(
                response,
                provider="deepseek",
                requested_model=model,
            )
            content = response.choices[0].message.content or "{}"
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                coach = parsed
                metering["model_output_used"] = True
        except Exception as e:
            metering["provider_status"] = "failed"
            logger.warning("LLM resume coach failed: %s", e)

    if coach is None:
        # 规则降级可整理用户已有原句，但不能补写数字、技能、范围或成果。
        fallback_suggestions = build_rule_based_rewrite_suggestions(resume_json)
        coach = {
            "summary": (
                "已完成基础诊断。当前没有可用的 AI 改写结果，"
                "下面只整理你已经写下的事实，不会补写技能、数字或成果。"
            ),
            "priority_actions": [
                "先查看下方的原文与修改版，确认语句是否准确",
                "如需更有说服力的版本，再补充真实的职责范围、方法和结果",
            ][:2],
            "suggestions": fallback_suggestions,
            "school_advice": gaps.get("education_gap"),
            "soft_skill_advice": (
                "与其写“沟通能力强”，不如说明你和谁协作、解决了什么问题，以及结果如何。"
            ),
        }

    battle_card = _build_battle_card(
        resume_json,
        company_name,
        role_family,
        target_job_title,
        gaps,
        jd_insight,
        hired_benchmark,
        coach,
    )

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
        "battle_card": battle_card,
        "_metering": metering,
    }

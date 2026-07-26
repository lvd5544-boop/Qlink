"""
岗位定制版简历：resume_variants + 5 种风格模板。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

STYLE_TEMPLATES: Dict[str, dict] = {
    "technical": {
        "id": "technical",
        "label": "技术深度型",
        "description": "突出技术栈、架构决策与性能指标",
        "prompt_hint": "强调技术方案、架构、性能优化与工程实践，用技术指标说话",
    },
    "result_driven": {
        "id": "result_driven",
        "label": "结果导向型",
        "description": "突出 KPI、业务成果与前后对比",
        "prompt_hint": "强调业务结果、转化率、成本节约、效率提升等 KPI",
    },
    "project_focus": {
        "id": "project_focus",
        "label": "项目亮点型",
        "description": "以项目为主线组织内容，突出代表性案例",
        "prompt_hint": "以项目为单位重组描述，每个项目写清背景、职责、亮点与成果",
    },
    "concise": {
        "id": "concise",
        "label": "简洁精炼型",
        "description": "短句要点式，适合一页简历",
        "prompt_hint": "精简表述，每段 2~3 个短句，去掉冗余修饰",
    },
    "balanced": {
        "id": "balanced",
        "label": "全面综合型",
        "description": "技术、项目、软实力均衡呈现",
        "prompt_hint": "平衡技术深度、项目成果与协作软实力，适合通用投递",
    },
}


def list_style_templates() -> List[dict]:
    return list(STYLE_TEMPLATES.values())


def _variant_label(target_job_title: str, style_id: str) -> str:
    title = (target_job_title or "通用").strip()
    style_label = STYLE_TEMPLATES.get(style_id, {}).get("label", style_id)
    return f"{title}版（{style_label}）"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "variant").strip().lower())
    return slug[:60] or "variant"


def _get_openai_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def _get_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _fallback_variant(
    resume_json: dict,
    target_job_title: str,
    style_id: str,
    job_json: Optional[dict] = None,
) -> dict:
    """无 LLM 时的规则化岗位定制。"""
    data = copy.deepcopy(resume_json or {})
    title = (target_job_title or data.get("expected_job_title") or "目标岗位").strip()
    style = STYLE_TEMPLATES.get(style_id, STYLE_TEMPLATES["balanced"])

    data["expected_job_title"] = title
    summary = (data.get("summary") or "").strip()
    if summary:
        data["summary"] = f"专注{title}方向。{summary}"
    else:
        data["summary"] = f"具备{title}相关经验，擅长核心业务开发与交付。"

    job_skills = []
    if job_json:
        for s in job_json.get("required_skills") or []:
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name:
                job_skills.append(name)

    existing = {
        (s.get("name") if isinstance(s, dict) else str(s)).lower()
        for s in (data.get("skills") or [])
    }
    for skill in job_skills[:5]:
        if skill.lower() not in existing:
            data.setdefault("skills", []).append({"name": skill, "level": "intermediate"})
            existing.add(skill.lower())

    if style_id == "project_focus":
        projects = data.get("projects") or []
        if projects and not any(
            (p.get("description") or "").strip() for p in projects if isinstance(p, dict)
        ):
            for p in projects:
                if isinstance(p, dict) and not (p.get("description") or "").strip():
                    p["description"] = (
                        f"负责{p.get('name', '核心模块')}开发与优化，交付关键功能并达成可量化成果"
                    )

    if style_id == "concise":
        for exp in data.get("work_experience") or []:
            if isinstance(exp, dict) and exp.get("description"):
                desc = exp["description"]
                exp["description"] = desc[:80] + ("…" if len(desc) > 80 else "")

    return data


async def generate_resume_variant(
    resume_json: dict,
    target_job_title: str,
    style_template: str = "balanced",
    job_json: Optional[dict] = None,
    job_title: str = "",
) -> dict:
    """
    生成岗位定制版 parsed_json。
    返回 variant_key、label、style_template、parsed_json。
    """
    style_id = style_template if style_template in STYLE_TEMPLATES else "balanced"
    style = STYLE_TEMPLATES[style_id]
    title = (
        target_job_title or job_title or resume_json.get("expected_job_title") or "通用岗位"
    ).strip()
    label = _variant_label(title, style_id)
    variant_key = _slugify(f"{title}_{style_id}")

    if not os.getenv("DEEPSEEK_API_KEY"):
        parsed = _fallback_variant(resume_json, title, style_id, job_json)
        return {
            "variant_key": variant_key,
            "label": label,
            "target_job_title": title,
            "style_template": style_id,
            "style_label": style["label"],
            "parsed_json": parsed,
            "source": "rule_fallback",
        }

    job_context = ""
    if job_json:
        job_context = f"""
【目标岗位 JD】
职位：{job_title or title}
技能要求：{json.dumps([s.get("name") if isinstance(s, dict) else s for s in job_json.get("required_skills", [])], ensure_ascii=False)}
职责：{json.dumps(job_json.get("responsibilities", [])[:6], ensure_ascii=False)}
"""

    prompt = f"""你是资深简历顾问。请基于原始简历，生成一份针对「{title}」的定制版简历 JSON。

【风格模板：{style["label"]}】
{style["prompt_hint"]}

【原则】
1. 不编造用户没有的经历或公司
2. 可调整 summary、技能排序、经历描述侧重点以匹配目标岗位
3. 描述尽量含量化指标；若原文无数字，保留原文表述
4. 输出与输入相同的 JSON Schema（name, email, phone, expected_job_title, summary, skills, work_experience, projects, education, school, degree, soft_skills 等）

{job_context}

【原始简历】
{json.dumps(resume_json, ensure_ascii=False)[:8000]}

严格输出 JSON 对象，不要 markdown 代码块。
"""

    try:
        from .llm_client import async_chat_completion, model_api_key

        if not model_api_key():
            raise RuntimeError("no_api_key")
        response = await async_chat_completion(
            messages=[
                {"role": "system", "content": "你只输出合法 JSON 对象，字段名英文。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
        )
        content = (response.choices[0].message.content or "{}").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content)
        parsed["expected_job_title"] = title
        return {
            "variant_key": variant_key,
            "label": label,
            "target_job_title": title,
            "style_template": style_id,
            "style_label": style["label"],
            "parsed_json": parsed,
            "source": "llm",
        }
    except Exception as e:
        logger.warning("LLM resume variant failed: %s", e)
        parsed = _fallback_variant(resume_json, title, style_id, job_json)
        return {
            "variant_key": variant_key,
            "label": label,
            "target_job_title": title,
            "style_template": style_id,
            "style_label": style["label"],
            "parsed_json": parsed,
            "source": "rule_fallback",
        }

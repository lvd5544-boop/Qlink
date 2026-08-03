"""
岗位定制版简历：resume_variants + 5 种风格模板。
PR10: 无 AI 时不虚构技能/成果；经 Model Gateway 调用模型。
"""

from __future__ import annotations

import copy
import html
import json
import logging
import re
from typing import Dict, List, Optional

from .ai.config import provider_configured
from .ai.errors import AIUnavailableError, SchemaValidationError
from .ai.gateway import InvocationContext, gateway_run

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
    title = html.unescape(target_job_title or "通用").strip()
    style_label = STYLE_TEMPLATES.get(style_id, {}).get("label", style_id)
    return f"{title}版（{style_label}）"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "variant").strip().lower())
    return slug[:60] or "variant"


def _safe_reorder_only(
    resume_json: dict,
    target_job_title: str,
    style_id: str,
) -> dict:
    """Rules-only path: reorder/truncate existing text; never invent facts."""
    data = copy.deepcopy(resume_json or {})
    title = (target_job_title or data.get("expected_job_title") or "目标岗位").strip()
    data["expected_job_title"] = title

    if style_id == "concise":
        for exp in data.get("work_experience") or []:
            if isinstance(exp, dict) and exp.get("description"):
                desc = exp["description"]
                exp["description"] = desc[:80] + ("…" if len(desc) > 80 else "")
    return data


def _unavailable_result(
    *,
    variant_key: str,
    label: str,
    title: str,
    style_id: str,
    style: dict,
    resume_json: dict,
) -> dict:
    return {
        "variant_key": variant_key,
        "label": label,
        "target_job_title": title,
        "style_template": style_id,
        "style_label": style["label"],
        "parsed_json": _safe_reorder_only(resume_json, title, style_id),
        "source": "ai_unavailable",
        "error_code": "ai_unavailable",
        "message": "AI 暂不可用。未新增任何经历、技能或成果；规则重排仍可用。",
    }


async def generate_resume_variant(
    resume_json: dict,
    target_job_title: str,
    style_template: str = "balanced",
    job_json: Optional[dict] = None,
    job_title: str = "",
    user_id: str | None = None,
) -> dict:
    """
    生成岗位定制版 parsed_json。
    返回 variant_key、label、style_template、parsed_json。
    """
    style_id = style_template if style_template in STYLE_TEMPLATES else "balanced"
    style = STYLE_TEMPLATES[style_id]
    title = html.unescape(
        target_job_title or job_title or resume_json.get("expected_job_title") or "通用岗位"
    ).strip()
    label = _variant_label(title, style_id)
    variant_key = _slugify(f"{title}_{style_id}")

    if not provider_configured():
        return _unavailable_result(
            variant_key=variant_key,
            label=label,
            title=title,
            style_id=style_id,
            style=style,
            resume_json=resume_json,
        )

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
1. 不编造用户没有的经历、公司、技能、数字或成果
2. 可调整 summary 措辞侧重、技能排序、经历描述侧重点以匹配目标岗位
3. 若原文无数字，保留原文表述，不得新增量化指标
4. 不得从 JD 复制技能到候选人 skills，除非原文已有
5. 输出与输入相同的 JSON Schema（name, email, phone, expected_job_title, summary, skills, work_experience, projects, education, school, degree, soft_skills 等）

{job_context}

【原始简历】
{json.dumps(resume_json, ensure_ascii=False)[:8000]}

严格输出 JSON 对象，不要 markdown 代码块。
"""

    try:
        result = await gateway_run(
            task="faithful_rewrite",
            payload={
                "messages": [
                    {
                        "role": "system",
                        "content": "你只输出合法 JSON 对象，字段名英文。禁止虚构经历与技能。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.35,
                "max_tokens": 4000,
            },
            schema=None,
            context=InvocationContext(user_id=user_id),
            require_json=True,
        )
        parsed = result.parsed if isinstance(result.parsed, dict) else json.loads(result.raw_text)
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
    except (AIUnavailableError, SchemaValidationError) as exc:
        logger.warning("resume variant AI unavailable/invalid: %s", type(exc).__name__)
        return _unavailable_result(
            variant_key=variant_key,
            label=label,
            title=title,
            style_id=style_id,
            style=style,
            resume_json=resume_json,
        )
    except Exception as exc:
        logger.warning("LLM resume variant failed: %s", type(exc).__name__)
        return _unavailable_result(
            variant_key=variant_key,
            label=label,
            title=title,
            style_id=style_id,
            style=style,
            resume_json=resume_json,
        )

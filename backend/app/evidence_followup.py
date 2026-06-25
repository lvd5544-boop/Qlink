"""
AI 证据追问：缺量化时生成 2~3 个追问，再根据用户回答生成带数字的 example_after。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from .resume_apply import patch_from_field_path
from .resume_health import _description_has_quantification
from .resume_suggestions import normalize_patch

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _get_openai_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def _get_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def get_entry_context(resume_json: dict, entry_type: str, index: int) -> dict:
    """解析工作经历或项目条目上下文。"""
    section = "work_experience" if entry_type == "work" else "projects"
    items = resume_json.get(section) or []
    if index < 0 or index >= len(items):
        raise ValueError(f"无效的{section}索引: {index}")
    item = items[index]
    if not isinstance(item, dict):
        raise ValueError("经历条目格式无效")

    name_key = "company" if section == "work_experience" else "name"
    field_path = f"{section}[{index}].description"
    description = (item.get("description") or "").strip()
    return {
        "entry_type": entry_type,
        "section": section,
        "index": index,
        "field_path": field_path,
        "name": item.get(name_key) or ("工作经历" if section == "work_experience" else "项目"),
        "role": item.get("position") or item.get("role") or "",
        "description": description,
        "needs_followup": not _description_has_quantification(description),
    }


def list_unquantified_entries(resume_json: dict) -> List[dict]:
    """返回所有缺量化的经历/项目条目。"""
    entries: List[dict] = []
    for entry_type in ("work", "project"):
        section = "work_experience" if entry_type == "work" else "projects"
        for idx, item in enumerate(resume_json.get(section) or []):
            if not isinstance(item, dict):
                continue
            ctx = get_entry_context(resume_json, entry_type, idx)
            if ctx["needs_followup"]:
                entries.append(ctx)
    return entries


def _fallback_questions(context: dict) -> List[dict]:
    name = context.get("name") or "该段经历"
    return [
        {
            "id": "scope",
            "question": f"在「{name}」中，你负责的业务/模块规模如何？（如日活、订单量、用户量等）",
            "hint": "例如：日订单 5 万单、服务 20 万用户",
        },
        {
            "id": "action",
            "question": "你采取了哪些关键动作或技术方案？",
            "hint": "例如：引入 Redis 缓存、重构核心接口",
        },
        {
            "id": "result",
            "question": "最终取得了哪些可量化结果？（比例、耗时、成本等）",
            "hint": "例如：接口 P99 降低 35%、转化率提升 18%",
        },
    ]


def generate_followup_questions(context: dict) -> List[dict]:
    """生成 2~3 个追问，缺量化时调用。"""
    if not context.get("needs_followup"):
        return []

    if not os.getenv("DEEPSEEK_API_KEY"):
        return _fallback_questions(context)

    prompt = f"""你是简历优化助手。以下经历描述缺少量化数据，请生成 2~3 个简短追问，帮助用户补充可验证的数字。

【经历】
公司/项目：{context.get('name')}
角色：{context.get('role')}
当前描述：{context.get('description') or '（暂无描述）'}

要求：
1. 每个问题聚焦一个维度（规模/动作/结果/协作范围等）
2. 不要建议编造，只追问用户可能记得的真实数据
3. 输出 JSON 数组，每项含 id、question、hint

格式示例：
[
  {{"id": "scope", "question": "...", "hint": "..."}},
  {{"id": "result", "question": "...", "hint": "..."}}
]
"""
    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": "你只输出合法 JSON 数组，不要 markdown。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "[]").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        questions = json.loads(content)
        if isinstance(questions, list) and 2 <= len(questions) <= 4:
            return questions[:3]
    except Exception as e:
        logger.warning("LLM followup questions failed: %s", e)

    return _fallback_questions(context)


def _extract_numbers_from_answers(answers: List[dict]) -> List[str]:
    nums: List[str] = []
    for item in answers:
        text = (item.get("answer") or "").strip()
        nums.extend(_NUMBER_RE.findall(text))
    return nums


def _fallback_regenerate(context: dict, answers: List[dict]) -> str:
    """无 LLM 时，根据用户回答拼接证据句。"""
    original = (context.get("description") or "").strip()
    answer_text = "；".join(
        (a.get("answer") or "").strip()
        for a in answers
        if (a.get("answer") or "").strip()
    )
    if original and answer_text:
        combined = f"{original}；{answer_text}"
    else:
        combined = answer_text or original

    if not _description_has_quantification(combined):
        nums = _extract_numbers_from_answers(answers)
        if nums:
            combined = f"{combined}，相关指标约 {nums[0]}"
        else:
            combined = (
                f"{combined}，通过优化核心流程使关键指标提升约 20%，"
                "支撑业务规模持续扩大（请根据实际数据调整）"
            )
    return combined.strip()


def regenerate_evidence_sentence(context: dict, answers: List[dict]) -> dict:
    """
    根据追问回答生成 example_after（含量化指标的证据句）。
    返回 example_before、example_after、field_path、patch。
    """
    example_before = (context.get("description") or "").strip() or "（暂无描述）"
    answer_block = "\n".join(
        f"- {a.get('question', a.get('id', ''))}: {a.get('answer', '')}"
        for a in answers
        if (a.get("answer") or "").strip()
    )

    example_after = ""
    if os.getenv("DEEPSEEK_API_KEY") and answer_block.strip():
        prompt = f"""你是简历优化助手。根据用户提供的真实数据，将经历改写为一条结果导向、含量化指标的中文描述。

【写作原则】
1. 只使用用户回答中的信息，不要编造用户未提供的数字
2. 必须包含至少 1 个具体数字（比例、规模、耗时、人数等）
3. 单段描述，80~150 字，不要列表
4. 若用户未提供数字，用「约 X%」等保守表述并标注需确认

公司/项目：{context.get('name')}
角色：{context.get('role')}
原文：{example_before}

【用户补充的数据】
{answer_block}

只输出改写后的描述文本，不要 JSON 或 markdown。
"""
        try:
            client = _get_openai_client()
            response = client.chat.completions.create(
                model=_get_model(),
                messages=[
                    {"role": "system", "content": "你只输出改写后的简历描述句。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            example_after = (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("LLM evidence regenerate failed: %s", e)

    if not example_after:
        example_after = _fallback_regenerate(context, answers)

    if not _description_has_quantification(example_after):
        example_after = _fallback_regenerate(context, answers)

    field_path = context["field_path"]
    patch = normalize_patch(patch_from_field_path(field_path, example_after))
    return {
        "example_before": example_before,
        "example_after": example_after,
        "field_path": field_path,
        "section": context["section"],
        "index": context["index"],
        "entry_type": context["entry_type"],
        "patch": patch,
        "has_quantification": _description_has_quantification(example_after),
    }

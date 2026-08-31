"""
AI 证据追问：信息不足时生成 2~3 个追问，再仅根据用户确认的信息生成 example_after。
"""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import List, Optional

from .resume_apply import patch_from_field_path
from .resume_health import _description_has_quantification
from .resume_suggestions import normalize_patch
from .faithful_expansion import (
    analyze_answers,
    build_claim_ledger,
    is_empty_answer,
)
from .provider_costs import extract_provider_usage
from .llm_client import default_model_name, model_api_key, sync_chat_completion
from .resume_writing_style import (
    compose_evidence_forward,
    normalize_style,
    serialize_style,
    style_prompt_contract,
)

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


# 默认严格模式：只整合原文与用户回答，不调用 LLM 扩写（防编造）
def _strict_mode_enabled() -> bool:
    return os.getenv("EVIDENCE_FOLLOWUP_STRICT", "true").lower() in ("1", "true", "yes")


def _get_model() -> str:
    return default_model_name("faithful_rewrite")


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


def _entry_claim_prefix(context: dict) -> str:
    """与 claim_reasoning._claim_id 对齐的条目前缀，如 work_experience_0_。"""
    section = context.get("section") or ""
    index = context.get("index")
    if section and index is not None:
        return f"{section}_{index}_"
    entry_type = context.get("entry_type")
    if entry_type == "work" and index is not None:
        return f"work_experience_{index}_"
    if entry_type == "project" and index is not None:
        return f"projects_{index}_"
    return ""


def _score_saved_record(
    record: dict,
    *,
    name: str,
    role: str,
    description: str,
    entry_corpus: str,
    claim_prefix: str = "",
) -> int:
    score = 0
    claim_id = (record.get("claim_id") or "").strip()
    # claim_id 主键优先：精确关联澄清 / 面试追问答案
    if claim_prefix and claim_id:
        if claim_id.startswith(claim_prefix):
            score += 10
        elif claim_id == claim_prefix.rstrip("_"):
            score += 10
    context_claim_id = ""  # filled by caller via record match only

    claim_text = (record.get("claim_text") or "").strip().lower()
    extra = (record.get("question") or record.get("answer") or "").strip().lower()
    record_blob = f"{claim_text} {extra}"

    if claim_text and len(claim_text) >= 4:
        if claim_text in description or description in claim_text:
            score += 4
        else:
            for i in range(max(0, len(claim_text) - 3)):
                chunk = claim_text[i : i + 4]
                if chunk in description:
                    score += 2
                    break

    if name and len(name) >= 2 and name in record_blob:
        score += 2
    if role and len(role) >= 2 and role in entry_corpus:
        score += 1
    if name and len(name) >= 2 and name in entry_corpus and name in record_blob:
        score += 1

    _ = context_claim_id  # silence unused
    return score


def _match_saved_records(
    resume_json: dict,
    context: dict,
    storage_key: str,
    *,
    question_fallback: Optional[str] = None,
) -> List[dict]:
    """将已保存回答与当前经历条目匹配；优先 claim_id，其次模糊匹配。"""
    saved = list(resume_json.get(storage_key) or [])
    if not saved:
        return []

    name = (context.get("name") or "").strip().lower()
    role = (context.get("role") or "").strip().lower()
    description = (context.get("description") or "").strip().lower()
    entry_corpus = f"{name} {role} {description}"
    claim_prefix = _entry_claim_prefix(context)
    explicit_claim_id = (context.get("claim_id") or "").strip()

    # 1) 精确 claim_id
    if explicit_claim_id:
        exact = [
            {
                **record,
                "match_score": 100,
                "match_type": "claim_id",
                "answer_turn_index": idx,
            }
            for idx, record in enumerate(saved)
            if (record.get("answer") or "").strip()
            and (record.get("claim_id") or "").strip() == explicit_claim_id
        ]
        if exact:
            return exact[:5]

    matched: List[dict] = []
    for idx, record in enumerate(saved):
        if not (record.get("answer") or "").strip():
            continue
        score = _score_saved_record(
            record,
            name=name,
            role=role,
            description=description,
            entry_corpus=entry_corpus,
            claim_prefix=claim_prefix,
        )
        # 条目级 claim_id 前缀匹配也算精确
        if claim_prefix and (record.get("claim_id") or "").startswith(claim_prefix):
            match_type = "claim_id_prefix"
        elif score >= 2:
            match_type = "entry"
        else:
            continue
        item = {
            **record,
            "match_score": score,
            "match_type": match_type,
            "answer_turn_index": idx,
        }
        if question_fallback and not item.get("question"):
            item["question"] = (
                record.get("claim_text") or record.get("job_title") or question_fallback
            )
        matched.append(item)

    if matched:
        matched.sort(key=lambda x: (-x.get("match_score", 0), x.get("saved_at") or ""))
        return matched[:5]

    # 严格模式下不返回无关「最近候选」，避免误填
    if _strict_mode_enabled():
        return []

    recent = [r for r in saved if (r.get("answer") or "").strip()][-3:]
    return [
        {
            **record,
            "match_score": 0,
            "match_type": "recent_candidate",
            "question": (
                record.get("question")
                or record.get("claim_text")
                or record.get("job_title")
                or question_fallback
                or "相关追问"
            ),
            "answer_turn_index": len(saved) - len(recent) + i,
        }
        for i, record in enumerate(recent)
    ]


def match_claim_followup_answers(resume_json: dict, context: dict) -> List[dict]:
    """
    将 AI 面试官保存的 claim 追问记录与当前经历条目做轻量匹配。
    精确匹配失败时返回最近 3 条候选，供用户手动一键填入（不自动采纳）。
    """
    return _match_saved_records(resume_json, context, "claim_followup_answers")


def match_clarification_answers(resume_json: dict, context: dict) -> List[dict]:
    """
    将招聘方澄清回复（clarification_answers）与当前经历条目做轻量匹配。
    供忠实改写一键填入使用。
    """
    return _match_saved_records(
        resume_json,
        context,
        "clarification_answers",
        question_fallback="招聘方澄清",
    )


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
公司/项目：{context.get("name")}
角色：{context.get("role")}
当前描述：{context.get("description") or "（暂无描述）"}

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
        if not model_api_key():
            return _fallback_questions(context)
        response = sync_chat_completion(
            model=_get_model(),
            messages=[
                {"role": "system", "content": "你只输出合法 JSON 数组，不要 markdown。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            task="claim_evidence_assess",
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
        logger.warning("LLM followup questions failed: %s", type(e).__name__)

    return _fallback_questions(context)


def _extract_numbers_from_answers(answers: List[dict]) -> List[str]:
    nums: List[str] = []
    for item in answers:
        text = (item.get("answer") or "").strip()
        nums.extend(_NUMBER_RE.findall(text))
    return nums


def _meaningful_answers(answers: List[dict]) -> List[str]:
    """过滤掉「没有/无」等空回答，只保留用户实际补充的内容。"""
    out: List[str] = []
    for item in answers:
        text = (item.get("answer") or "").strip()
        if text and not is_empty_answer(text):
            out.append(text)
    return out


def analyze_followup_answers(context: dict, answers: List[dict]) -> dict:
    """语义澄清分析（采纳前预览）。"""
    return analyze_answers(context, answers)


def _strict_compose_evidence(
    context: dict,
    answers: List[dict],
    style_template: str = "evidence_forward",
) -> str:
    """
    严格忠实模式：仅整合「原文 + 用户回答」，不添加任何新职责/技术/成果。
    不做润色扩写，不注入模板数字。
    """
    _ = normalize_style(style_template)
    return compose_evidence_forward(
        context,
        answers,
        is_empty_answer=is_empty_answer,
    )


def _source_corpus(context: dict, answers: List[dict]) -> str:
    """用于忠实度校验的允许词库：原文 + 用户回答 + 公司/角色名。"""
    chunks = [
        context.get("description") or "",
        context.get("name") or "",
        context.get("role") or "",
        *_meaningful_answers(answers),
    ]
    return " ".join(chunks)


_FIDELITY_VERSION = "pr5.1-rules-v2"
_ROLE_STRENGTH = {
    "协助": 1,
    "参与": 1,
    "配合": 1,
    "负责": 2,
    "推动": 2,
    "主导": 3,
    "牵头": 3,
    "带领": 3,
    "负责人": 3,
}
_SYNONYM_NORMALIZATION = {
    "开发": "研发",
    "优化": "改进",
    "策略": "方案",
    "搭建": "建设",
    "构建": "建设",
    "完成": "实现",
}
_GRAMMATICAL_INSERT_CHARS = frozenset("并且与和及的了在将把为对从中由")


def _normalize_fidelity_text(text: str) -> str:
    value = (text or "").lower()
    for source, target in _SYNONYM_NORMALIZATION.items():
        value = value.replace(source, target)
    return re.sub(r"[\s，,。；;：:！？!?\-—（）()【】\[\]「」“”\"'、]+", "", value)


def _protected_facts(text: str) -> set[str]:
    value = (text or "").lower()
    patterns = (
        r"\d+(?:\.\d+)?\s*(?:%|％|万元|万|元|美元|usd|人|次|个|天|周|月|年|小时|分钟|ms|s|qps|倍)?",
        r"[一二三四五六七八九十百千万两]+成",
        r"(?:19|20)\d{2}年?(?:\d{1,2}月)?",
        r"(?:¥|￥|\$)\s*\d+(?:\.\d+)?",
        r"[a-z][a-z0-9.+#_-]{1,}",
    )
    facts: set[str] = set()
    for pattern in patterns:
        facts.update(match.strip() for match in re.findall(pattern, value, flags=re.I))
    return {fact for fact in facts if fact}


def _max_role_strength(text: str) -> int:
    return max(
        (strength for role, strength in _ROLE_STRENGTH.items() if role in (text or "")),
        default=0,
    )


def _ngram_coverage(source: str, generated: str, size: int = 2) -> float:
    src = _normalize_fidelity_text(source)
    gen = _normalize_fidelity_text(generated)
    if not gen:
        return 1.0
    if len(gen) < size:
        return 1.0 if gen in src else 0.0
    grams = [gen[index : index + size] for index in range(len(gen) - size + 1)]
    return sum(1 for gram in grams if gram in src) / len(grams)


def _unsupported_insertions(source: str, generated: str) -> list[str]:
    """找出被高重合率掩盖的新增事实短语。

    n-gram 总覆盖率无法可靠发现长句中插入的中文专名或技术名。这里仅检查
    SequenceMatcher 明确标记为 ``insert`` 的片段；单个连接词允许出现，
    替换和重排仍由受保护事实、角色强度与覆盖率规则处理。
    """
    src = _normalize_fidelity_text(source)
    gen = _normalize_fidelity_text(generated)
    if not src or not gen:
        return []

    unsupported: list[str] = []
    matcher = SequenceMatcher(a=src, b=gen, autojunk=False)
    for opcode, _src_start, _src_end, gen_start, gen_end in matcher.get_opcodes():
        if opcode != "insert":
            continue
        inserted = gen[gen_start:gen_end]
        meaningful = "".join(char for char in inserted if char not in _GRAMMATICAL_INSERT_CHARS)
        if len(meaningful) >= 2 and inserted not in src:
            unsupported.append(inserted)
    return unsupported


def assess_fidelity(source: str, generated: str) -> dict:
    """对每个原子片段和受保护事实做可解释、确定性的来源覆盖检查。"""
    if not generated or not source:
        return {
            "version": _FIDELITY_VERSION,
            "violated": bool(generated and not source),
            "coverage": 0.0 if generated and not source else 1.0,
            "reasons": ["missing_source"] if generated and not source else [],
            "evidence_facts": [],
        }

    reasons: list[str] = []
    source_facts = _protected_facts(source)
    generated_facts = _protected_facts(generated)
    unsupported_facts = sorted(generated_facts - source_facts)
    if unsupported_facts:
        reasons.append(f"unsupported_protected_facts:{','.join(unsupported_facts)}")

    if _max_role_strength(generated) > _max_role_strength(source):
        reasons.append("role_escalation")

    unsupported_insertions = _unsupported_insertions(source, generated)
    if unsupported_insertions:
        reasons.append(f"unsupported_inserted_span:{','.join(unsupported_insertions)}")

    atomic_segments = [
        segment.strip()
        for segment in re.split(r"[；;。！？!?\n，,]+", generated)
        if segment.strip()
    ]
    segment_coverages = [
        _ngram_coverage(source, segment)
        for segment in atomic_segments
        if len(_normalize_fidelity_text(segment)) >= 4
    ]
    low_coverage = [value for value in segment_coverages if value < 0.55]
    if low_coverage:
        reasons.append("unsupported_atomic_segment")

    coverage = _ngram_coverage(source, generated)
    if len(_normalize_fidelity_text(generated)) >= 8 and coverage < 0.62:
        reasons.append("insufficient_source_coverage")

    return {
        "version": _FIDELITY_VERSION,
        "violated": bool(reasons),
        "coverage": round(coverage, 4),
        "segment_coverages": [round(value, 4) for value in segment_coverages],
        "reasons": reasons,
        "evidence_facts": sorted(source_facts),
        "unsupported_facts": unsupported_facts,
        "unsupported_insertions": unsupported_insertions,
    }


def _fidelity_violated(source: str, generated: str) -> bool:
    return bool(assess_fidelity(source, generated)["violated"])


def _fallback_regenerate(
    context: dict,
    answers: List[dict],
    style_template: str = "evidence_forward",
) -> str:
    """规则兜底：严格拼接，不注入虚构指标。"""
    return _strict_compose_evidence(context, answers, style_template)


REWRITE_MODES = ("conservative", "standard", "assertive")

REWRITE_MODE_LABELS = {
    "conservative": "保守版",
    "standard": "标准版",
    "assertive": "进取版",
}


def _normalize_rewrite_mode(mode: str) -> str:
    m = (mode or "standard").strip().lower()
    return m if m in REWRITE_MODES else "standard"


def _assess_rewrite_mode_risk(mode: str, answers: List[dict], semantic_analysis: dict) -> tuple:
    warnings: List[str] = []
    meaningful = _meaningful_answers(answers)
    has_numbers = bool(_extract_numbers_from_answers(answers))
    has_factual = any(
        a.get("intent") == "factual" for a in (semantic_analysis.get("answer_analysis") or [])
    )

    if mode == "assertive":
        if not has_factual or not meaningful:
            warnings.append(
                "进取版需要您明确说明角色、动作与结果，当前证据不足，建议改用标准版或保守版"
            )
        elif not has_numbers:
            warnings.append("进取版强调影响力，建议补充量化指标后再使用")
    elif mode == "standard" and not meaningful:
        warnings.append("标准版需要至少一条有效回答，当前内容不足")

    if semantic_analysis.get("needs_clarification"):
        warnings.extend(semantic_analysis["needs_clarification"][:2])

    risk = "low"
    if mode == "assertive" and (not has_factual or warnings):
        risk = "high"
    elif mode == "assertive":
        risk = "medium"
    elif warnings:
        risk = "medium"

    return risk, warnings


def _compose_by_mode(
    mode: str,
    context: dict,
    answers: List[dict],
    example_before: str,
    answer_block: str,
    source_corpus: str,
    style_template: str,
) -> tuple[str, dict]:
    metering = {
        "model_called": False,
        "provider_status": None,
        "provider_usage": None,
        "model_output_used": False,
    }
    if mode == "conservative":
        return _strict_compose_evidence(context, answers, style_template), metering

    if not os.getenv("DEEPSEEK_API_KEY") or not answer_block.strip():
        return _strict_compose_evidence(context, answers, style_template), metering

    if mode == "standard":
        system = "你只编辑用户已有信息，使其具体、主动、事实化、便于招聘方快速扫描；绝不新增事实。输出中文。"
        constraints = """【标准版约束】
1. 禁止添加用户未提及的职责、技术、项目、成果
2. 禁止编造数字；数字只能来自原文或用户补充
3. 允许：调整语序、合并重复、去掉口语词、突出已有动作和已有结果
4. 不允许：扩写、推断、补全新事实"""
        temperature = 0.2
    else:
        system = "你只编辑用户已有信息，可更清晰地呈现已证实影响，但绝不编造或升级角色。输出中文。"
        constraints = """【进取版约束 — 仅在用户已明确角色/动作/结果时生效】
1. 禁止添加用户未提及的职责、技术、项目、成果
2. 禁止编造数字
3. 只有来源原文明确支持时，才可使用更强动作动词
4. 若用户未明确说明角色/动作/结果，不得强化影响力"""
        temperature = 0.25

    prompt = f"""你是简历整理助手。将「原文」与「用户补充」整合为一条中文经历描述。

{constraints}

{style_prompt_contract(style_template)}

公司/项目：{context.get("name")}
角色：{context.get("role")}
原文：{example_before}

【用户补充的数据】
{answer_block}

只输出一条整合后的描述，不要 JSON、markdown 或英文。
"""
    try:
        if not model_api_key():
            return _strict_compose_evidence(context, answers, style_template), metering
        metering["model_called"] = True
        response = sync_chat_completion(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            task="faithful_rewrite",
        )
        metering["provider_status"] = "succeeded"
        metering["provider_usage"] = extract_provider_usage(
            response,
            provider="deepseek",
            requested_model=_get_model(),
        )
        candidate = (response.choices[0].message.content or "").strip()
        if candidate and not _fidelity_violated(source_corpus, candidate):
            metering["model_output_used"] = True
            return candidate, metering
        logger.warning("LLM evidence output failed fidelity check, using strict compose")
    except Exception as e:
        metering["provider_status"] = "failed"
        logger.warning("LLM evidence regenerate failed: %s", type(e).__name__)

    return _strict_compose_evidence(context, answers, style_template), metering


def regenerate_evidence_sentence(
    context: dict,
    answers: List[dict],
    rewrite_mode: str = "standard",
    style_template: str = "evidence_forward",
) -> dict:
    """
    根据追问回答生成 example_after。
    rewrite_mode: conservative | standard | assertive
    EVIDENCE_FOLLOWUP_STRICT=true 时强制 conservative（仅拼接，不调用 LLM）。
    """
    mode = _normalize_rewrite_mode(rewrite_mode)
    style_template = normalize_style(style_template)
    if _strict_mode_enabled():
        # 严格模式：强制保守拼接，杜绝 LLM 扩写引入未经验证内容
        mode = "conservative"

    example_before = (context.get("description") or "").strip() or "（暂无描述）"
    answer_block = "\n".join(
        f"- {a.get('question', a.get('id', ''))}: {a.get('answer', '')}"
        for a in answers
        if (a.get("answer") or "").strip()
    )

    source_corpus = _source_corpus(context, answers)
    semantic_analysis = analyze_answers(context, answers)
    mode_risk_level, mode_warnings = _assess_rewrite_mode_risk(mode, answers, semantic_analysis)

    if _strict_mode_enabled() and not _meaningful_answers(answers):
        mode_warnings = list(mode_warnings) + ["严格模式：请先填写真实证据后再生成改写"]
        mode_risk_level = "high"

    example_after, metering = _compose_by_mode(
        mode,
        context,
        answers,
        example_before,
        answer_block,
        source_corpus,
        style_template,
    )
    if not example_after:
        example_after = _fallback_regenerate(context, answers, style_template)

    field_path = context["field_path"]
    patch = normalize_patch(patch_from_field_path(field_path, example_after))
    claim_ledger = build_claim_ledger(example_before, answers, example_after)
    fidelity_result = assess_fidelity(source_corpus, example_after)
    evidence_references = [
        str(reference)
        for answer in answers
        for reference in (answer.get("evidence_id"), answer.get("id"), answer.get("claim_id"))
        if reference
    ]
    patch["fidelity_result"] = fidelity_result
    patch["evidence_references"] = list(dict.fromkeys(evidence_references))

    fidelity_notes = {
        "conservative": "保守版：仅拼接原文与您填写的内容，不强化影响力，适合证据不足时。",
        "standard": "标准版：职业化表达，重组语序与去口语化，不新增事实。",
        "assertive": "进取版：更突出影响力与岗位匹配，仅基于您已说明的角色/动作/结果。",
    }

    return {
        "example_before": example_before,
        "example_after": example_after,
        "field_path": field_path,
        "section": context["section"],
        "index": context["index"],
        "entry_type": context["entry_type"],
        "patch": patch,
        "has_quantification": _description_has_quantification(example_after),
        "strict_mode": _strict_mode_enabled() or mode == "conservative",
        "rewrite_mode": mode,
        "rewrite_mode_label": REWRITE_MODE_LABELS.get(mode, mode),
        "mode_risk_level": mode_risk_level,
        "mode_warnings": mode_warnings,
        "claim_ledger": claim_ledger,
        "evidence_references": patch["evidence_references"],
        "fidelity_result": fidelity_result,
        "semantic_analysis": semantic_analysis,
        "fidelity_note": fidelity_notes.get(mode),
        **serialize_style(style_template),
        "_metering": metering,
    }

"""
求职者侧：语义忠实扩写引擎。
- 回答意图识别（factual / negative / vague / evasive / packaging）
- 语义解读预览（表层含义 / 可能真实含义 / 待澄清点）
- Claim Ledger：输出每段文字的来源追溯
"""

from __future__ import annotations

import re
from typing import List

# 常见「包装词」— 本身不造假，但需追问具体边界
PACKAGING_WORDS = [
    "主导",
    "负责",
    "深度参与",
    "全面负责",
    "独立负责",
    "带领团队",
    "从0到1",
    "从 0 到 1",
    "闭环",
    "赋能",
    "打通",
    "沉淀",
    "显著",
    "大幅",
    "极大",
    "有效",
    "持续优化",
    "体系化建设",
    "leaded",
    "owned",
    "drove",
    "spearheaded",
]

# 机构/模板化简历常见句式（同质化检测，供候选人侧提醒）
TEMPLATE_PHRASES = [
    "具备良好的沟通协调能力",
    "具备较强的学习能力",
    "熟悉敏捷开发流程",
    "负责核心业务开发与维护",
    "参与需求分析与技术方案设计",
    "推动项目按时高质量交付",
    "跨部门协作",
    "结果导向",
    "用户增长体系建设",
    "全链路",
    "降本增效",
]

_EMPTY_ANSWER_PHRASES = frozenset(
    {
        "没有",
        "无",
        "暂无",
        "不详",
        "不了解",
        "无成果",
        "none",
        "n/a",
        "na",
        "无数据",
    }
)

_VAGUE_PATTERNS = [
    re.compile(r"^(相关|这块|一些|若干|大概|差不多|还行|一般)"),
    re.compile(r"(等等|之类|什么的|左右)$"),
    re.compile(r"^参与(了)?$"),
]


def is_empty_answer(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if t in _EMPTY_ANSWER_PHRASES:
        return True
    if t.startswith("没有") and len(t) <= 10:
        return True
    return False


def classify_answer_intent(text: str) -> dict:
    """单条回答意图分类。"""
    t = (text or "").strip()
    if not t:
        return {"intent": "empty", "confidence": "high", "note": "未填写"}
    if is_empty_answer(t):
        return {"intent": "negative", "confidence": "high", "note": "用户明确表示无相关数据/成果"}
    for pat in _VAGUE_PATTERNS:
        if pat.search(t):
            return {
                "intent": "vague",
                "confidence": "medium",
                "note": "表述较模糊，建议追问具体范围",
            }
    packaging_hits = [w for w in PACKAGING_WORDS if w in t]
    if packaging_hits:
        return {
            "intent": "packaging",
            "confidence": "medium",
            "note": f"含包装词「{'、'.join(packaging_hits[:3])}」，需澄清实际职责边界",
            "packaging_words": packaging_hits,
        }
    if len(t) < 4:
        return {"intent": "vague", "confidence": "medium", "note": "回答过短，信息不足"}
    if re.search(r"\d", t):
        return {"intent": "factual", "confidence": "high", "note": "含具体数据或事实描述"}
    return {"intent": "factual", "confidence": "medium", "note": "有事实描述但缺少数字"}


def detect_packaging_in_text(text: str) -> List[str]:
    return [w for w in PACKAGING_WORDS if w in (text or "")]


def detect_template_phrases(text: str) -> List[str]:
    return [p for p in TEMPLATE_PHRASES if p in (text or "")]


def analyze_answers(context: dict, answers: List[dict]) -> dict:
    """
    语义澄清分析：在用户确认生成前，展示系统如何理解其回答。
    """
    original = (context.get("description") or "").strip()
    role = context.get("role") or ""
    name = context.get("name") or ""

    answer_analysis: List[dict] = []
    needs_clarification: List[str] = []
    ambiguities: List[str] = []

    for item in answers:
        q = item.get("question") or item.get("id") or ""
        a = (item.get("answer") or "").strip()
        intent_info = classify_answer_intent(a)
        entry = {"question": q, "answer": a, **intent_info}
        answer_analysis.append(entry)

        if intent_info["intent"] == "negative":
            ambiguities.append(f"关于「{q}」您表示无相关数据，系统将不在此维度补充成果")
        elif intent_info["intent"] == "vague":
            needs_clarification.append(f"「{q}」的回答较模糊，建议补充具体范围或数字")
        elif intent_info["intent"] == "packaging":
            needs_clarification.append(
                f"「{q}」含包装表述，建议说明您是负责人、核心成员还是协助参与"
            )

    # 对原文做三层解读（规则版，不调用 LLM）
    surface_meaning = original or "（暂无描述）"
    possible_meanings: List[str] = []
    if "负责" in original or "主导" in original:
        possible_meanings = [
            "您可能是该模块/项目的负责人或核心执行者",
            "您可能只是参与其中一部分，用了「负责/主导」等概括性表述",
            "您可能是协作角色，具体边界需进一步说明",
        ]
    elif original:
        possible_meanings = [
            "描述的是日常职责或参与范围",
            "可能省略了量化成果或具体产出",
        ]
    else:
        possible_meanings = ["当前无文字描述，完全依赖您的追问回答"]

    unclear_areas: List[str] = []
    if role and any(w in original for w in ("负责", "主导", "带领")):
        unclear_areas.append("是否有决策权？是负责人还是成员？")
    if not re.search(r"\d", original + " ".join(a.get("answer", "") for a in answers)):
        unclear_areas.append("目前仍缺少可量化数字（比例、规模、人数、耗时等）")
    if detect_packaging_in_text(original):
        unclear_areas.append("原文含包装词，实际职责边界不明确")

    # 系统将如何整合（预览理解）
    meaningful = [
        (a.get("answer") or "").strip()
        for a in answers
        if (a.get("answer") or "").strip() and not is_empty_answer(a.get("answer") or "")
    ]
    if original and meaningful:
        interpretation_summary = (
            f"将保留原文「{original[:40]}{'…' if len(original) > 40 else ''}」，"
            f"并整合您补充的 {len(meaningful)} 条信息；可能调整顺序，但不添加您未提及的职责或技术。"
        )
    elif meaningful:
        interpretation_summary = f"将仅使用您补充的 {len(meaningful)} 条信息组成描述。"
    else:
        interpretation_summary = "您未提供有效补充，建议返回填写或保留原文。"

    return {
        "entry_name": name,
        "role": role,
        "surface_meaning": surface_meaning,
        "possible_meanings": possible_meanings,
        "unclear_areas": unclear_areas,
        "answer_analysis": answer_analysis,
        "needs_clarification": needs_clarification,
        "ambiguities": ambiguities,
        "interpretation_summary": interpretation_summary,
        "packaging_words_in_original": detect_packaging_in_text(original),
        "template_phrases_in_original": detect_template_phrases(original),
        "ready_to_compose": len(meaningful) > 0 or bool(original),
    }


def build_claim_ledger(
    original: str,
    answers: List[dict],
    composed: str,
) -> List[dict]:
    """
    Claim Ledger：追溯 composed 中每段信息的来源。
    source: original | user_answer | system_compose（仅连接词，无新事实）
    """
    ledger: List[dict] = []
    if original and original.strip() and original.strip() in composed:
        ledger.append(
            {
                "text": original.strip(),
                "source": "original",
                "label": "简历原文",
                "verifiable": True,
            }
        )

    for item in answers:
        a = (item.get("answer") or "").strip()
        if not a or is_empty_answer(a):
            continue
        if a in composed:
            ledger.append(
                {
                    "text": a,
                    "source": "user_answer",
                    "label": "您的追问回答",
                    "question": item.get("question") or item.get("id"),
                    "verifiable": True,
                }
            )

    # 标记未能追溯到用户输入的部分（潜在风险）
    traced = " ".join(entry["text"] for entry in ledger)
    if composed and composed not in traced and composed != original:
        extra = composed
        for entry in ledger:
            extra = extra.replace(entry["text"], "", 1)
        extra = re.sub(r"[；;，,\s]+", "", extra)
        if len(extra) > 4:
            ledger.append(
                {
                    "text": composed,
                    "source": "unverified",
                    "label": "未能完全追溯来源",
                    "verifiable": False,
                }
            )

    return ledger

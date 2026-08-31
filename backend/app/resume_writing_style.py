"""Versioned, source-constrained resume writing styles.

The default style synthesizes the shared, non-proprietary principles in the
candidate-provided Resume Guide and Harvard FAS resume guidance: specific,
active, factual, concise, scan-friendly language; action + task + context/result.
It never supplies a verb, metric, keyword, or accomplishment that is absent
from the candidate's source material.
"""

from __future__ import annotations

import re
from typing import Any

STYLE_VERSION = "evidence_forward_v1"
DEFAULT_STYLE = "evidence_forward"
STYLE_LABELS = {DEFAULT_STYLE: "证据优先·招聘方易读"}

_ACTION_PREFIX_RE = re.compile(
    r"^(?:负责|参与|协助|配合|主导|牵头|带领|开发|设计|实现|构建|搭建|维护|"
    r"优化|分析|组织|协调|管理|撰写|编辑|研究|测试|交付|支持|处理|教授|培训|"
    r"develop(?:ed|ing)?|design(?:ed|ing)?|implement(?:ed|ing)?|build|built|"
    r"manage(?:d|ing)?|analy[sz](?:ed|ing)?|coordinate(?:d|ing)?|organize(?:d|ing)?|"
    r"write|wrote|edit(?:ed|ing)?|research(?:ed|ing)?|test(?:ed|ing)?|support(?:ed|ing)?)"
    r"(?:\s|[，,:：]|$)",
    re.IGNORECASE,
)

_CATEGORY_TERMS = {
    "action": ("action", "task", "method", "approach", "solution", "动作", "方案", "方法"),
    "context": ("scope", "scale", "context", "team", "范围", "规模", "协作"),
    "result": ("result", "outcome", "impact", "metric", "结果", "成果", "指标"),
}


def normalize_style(style_template: str | None) -> str:
    value = str(style_template or DEFAULT_STYLE).strip().lower()
    return value if value in STYLE_LABELS else DEFAULT_STYLE


def _answer_category(answer: dict[str, Any]) -> str:
    key = f"{answer.get('id') or ''} {answer.get('question') or ''}".casefold()
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in key for term in terms):
            return category
    return "detail"


def _dedupe_exact(parts: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = str(part or "").strip()
        fingerprint = re.sub(r"[\s；;。]+$", "", value).casefold()
        if not value or not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(value)
    return result


def compose_evidence_forward(
    context: dict[str, Any],
    answers: list[dict[str, Any]],
    *,
    is_empty_answer,
) -> str:
    """Order exact source spans into action → task → context → result.

    This deterministic path intentionally preserves source text verbatim. It
    changes only ordering and punctuation, so it remains usable when model
    generation is disabled.
    """
    original = str(context.get("description") or "").strip()
    if original == "（暂无描述）":
        original = ""

    grouped: dict[str, list[str]] = {
        "action": [],
        "context": [],
        "result": [],
        "detail": [],
    }
    for answer in answers:
        text = str(answer.get("answer") or "").strip()
        if not text or is_empty_answer(text):
            continue
        grouped[_answer_category(answer)].append(text)

    parts: list[str] = []
    if original and _ACTION_PREFIX_RE.search(original):
        parts.append(original)
        parts.extend(grouped["action"])
    else:
        parts.extend(grouped["action"])
        if original:
            parts.append(original)
    parts.extend(grouped["detail"])
    parts.extend(grouped["context"])
    parts.extend(grouped["result"])

    ordered = _dedupe_exact(parts)
    return "；".join(ordered).strip() or original or "（暂无描述）"


def style_prompt_contract(style_template: str | None) -> str:
    """Return the generation contract; it is guidance, never a fact source."""
    _ = normalize_style(style_template)
    return """【证据优先·招聘方易读句式】
1. 使用一条简洁、便于快速扫描的经历 bullet；不用第一人称
2. 优先采用「动作 + 任务 + 方法/范围 + 已证实结果」顺序
3. 使用主动、具体、事实化语言，避免华丽形容词和通用能力口号
4. 动词强度必须与原文和用户回答一致；不得把参与/协助升级为主导/带领
5. 数字、技能、关键词、职责、对象、范围和结果只能来自允许来源
6. 没有结果或数字时自然省略，不使用占位符，也不暗示缺失内容"""


def serialize_style(style_template: str | None) -> dict[str, str]:
    style = normalize_style(style_template)
    return {
        "style_template": style,
        "style_label": STYLE_LABELS[style],
        "style_version": STYLE_VERSION,
        "sentence_pattern": "Action + Task + Context/Result（仅使用已有证据）",
    }

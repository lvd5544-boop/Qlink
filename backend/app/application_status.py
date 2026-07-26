"""申请状态与澄清消息常量。"""

from __future__ import annotations

from typing import List, Optional

APPLICATION_STATUSES = frozenset(
    {
        "submitted",
        "viewed",
        "needs_clarification",
        "clarified",
        "clarification_closed",
        "interview_invited",
        "rejected",
        "accepted",
    }
)

STATUS_LABELS = {
    "submitted": "已申请",
    "viewed": "招聘方已查看",
    "needs_clarification": "待补充说明",
    "clarified": "已提交说明",
    "clarification_closed": "招聘方已关闭澄清",
    "interview_invited": "已收到面试邀请",
    "rejected": "未进入后续流程",
    "accepted": "已录用",
}

EMPLOYER_STATUS_LABELS = {
    "submitted": "新申请",
    "viewed": "已查看",
    "needs_clarification": "等待候选人说明",
    "clarified": "候选人已说明，待复核",
    "clarification_closed": "已关闭，候选人未说明",
    "interview_invited": "已发送面试邀请",
    "rejected": "已拒绝",
    "accepted": "已录用",
}

CLARIFICATION_REQUEST_PREFIX = "[澄清请求]"
CLARIFICATION_RESPONSE_PREFIX = "[澄清回复]"


def build_clarification_message(
    claim_text: str,
    questions: list,
    evidence_suggestions: Optional[List[str]] = None,
) -> str:
    qs = "；".join(q for q in questions if q)
    evidence = "、".join(e for e in (evidence_suggestions or []) if e)
    parts = [
        CLARIFICATION_REQUEST_PREFIX,
        f"关于 claim：「{claim_text}」",
        f"请补充说明：{qs}" if qs else "请补充说明相关细节。",
    ]
    if evidence:
        parts.append(f"建议准备证据：{evidence}")
    return "\n".join(parts)


def build_clarification_response_message(body: str) -> str:
    return f"{CLARIFICATION_RESPONSE_PREFIX}\n{body.strip()}"


def classify_message_body(body: str, message_kind: Optional[str] = None) -> str:
    known = {
        "clarification_request",
        "clarification_response",
        "text",
        "interview_invite",
        "interview_summary",
    }
    if message_kind in known:
        return message_kind
    text = (body or "").strip()
    if text.startswith(CLARIFICATION_REQUEST_PREFIX):
        return "clarification_request"
    if text.startswith(CLARIFICATION_RESPONSE_PREFIX):
        return "clarification_response"
    if text.startswith("[面试邀请]"):
        return "interview_invite"
    if text.startswith("[AI面试纪要"):
        return "interview_summary"
    return "text"


def clarification_request_meta(
    claim_text: str,
    questions: list,
    claim_id: Optional[str] = None,
    evidence_suggestions: Optional[List[str]] = None,
) -> dict:
    return {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "questions": [q for q in questions if q],
        "evidence_suggestions": [e for e in (evidence_suggestions or []) if e],
    }


def clarification_response_meta(
    claim_id: Optional[str] = None,
    claim_text: Optional[str] = None,
    request_message_id: Optional[str] = None,
) -> dict:
    meta = {}
    if claim_id:
        meta["claim_id"] = claim_id
    if claim_text:
        meta["claim_text"] = claim_text
    if request_message_id:
        meta["request_message_id"] = request_message_id
    return meta


def extract_claim_text_from_body(body: str) -> Optional[str]:
    """从澄清请求正文提取 claim 文本（兼容旧前缀格式）。"""
    import re

    text = (body or "").strip()
    match = re.search(r"关于 claim：「(.+?)」", text)
    return match.group(1) if match else None

"""履历审计共用评分与状态文案。"""

from __future__ import annotations

from typing import List

STATUS_LABELS = {
    "clear": "未发现明显需澄清项",
    "needs_clarification": "存在需澄清项，建议追问",
    "manual_review": "建议人工复核",
}


def compute_risk_score(items: List[dict], *, level_key: str = "severity") -> int:
    """按 high/medium/low 累加风险分，上限 100。"""
    score = 0
    for item in items:
        level = item.get(level_key) or item.get("risk_level") or "low"
        if level == "high":
            score += 25
        elif level == "medium":
            score += 15
        else:
            score += 8
    return min(100, score)

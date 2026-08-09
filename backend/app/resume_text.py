"""简历文本切分小工具。"""

from __future__ import annotations

import re
from typing import List

_EXPLICIT_BULLET = re.compile(r"^\s*(?:[-•●▪◦‣]|(?:\d{1,2}|[A-Za-z])[.)、])\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?])\s+|(?<=[.])\s+(?=[A-Z\u4e00-\u9fff])")


def _compact_visual_lines(text: str) -> list[str]:
    """Rebuild semantic paragraphs after PDF/DOCX visual line wrapping.

    A plain newline in an extracted resume usually means "the renderer wrapped
    this line", not "the author created another claim". Only explicit bullets
    start a new unit. This prevents a project paragraph from turning into a
    handful of orphaned sentence fragments.
    """
    lines = [re.sub(r"\s+", " ", row).strip() for row in (text or "").splitlines()]
    lines = [row for row in lines if row]
    if not lines:
        return []
    paragraphs: list[str] = []
    current = ""
    for row in lines:
        explicit = bool(_EXPLICIT_BULLET.match(row))
        cleaned = _EXPLICIT_BULLET.sub("", row).strip()
        if explicit and current:
            paragraphs.append(current.strip())
            current = cleaned
        else:
            current = f"{current} {cleaned}".strip()
    if current:
        paragraphs.append(current.strip())
    return paragraphs


def split_bullets(text: str) -> List[str]:
    if not text:
        return []
    units: list[str] = []
    for paragraph in _compact_visual_lines(text):
        clauses = [value.strip() for value in re.split(r"[；;]+", paragraph) if value.strip()]
        for clause in clauses:
            sentences = [
                value.strip() for value in _SENTENCE_BOUNDARY.split(clause) if value.strip()
            ]
            units.extend(sentences or [clause])

    # Reattach short visual fragments to their neighbour. A standalone claim
    # such as "out to achieve the highest R²..." has no useful local meaning.
    merged: list[str] = []
    for unit in units:
        word_count = len(re.findall(r"\b[\w²]+\b", unit))
        is_fragment = len(unit) < 28 or (
            re.match(r"^(?:and|or|but|to|for|with|via|out)\b", unit, re.I) and word_count < 18
        )
        if is_fragment and merged:
            merged[-1] = f"{merged[-1]} {unit}".strip()
        else:
            merged.append(unit)
    if len(merged) > 1 and len(merged[0]) < 24:
        merged[1] = f"{merged[0]} {merged[1]}".strip()
        merged.pop(0)
    return merged

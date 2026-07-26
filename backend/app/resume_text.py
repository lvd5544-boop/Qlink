"""简历文本切分小工具。"""

from __future__ import annotations

import re
from typing import List

_BULLET_SPLIT = re.compile(r"[；;\n]+")


def split_bullets(text: str) -> List[str]:
    if not text:
        return []
    return [p.strip() for p in _BULLET_SPLIT.split(text.strip()) if p.strip()]

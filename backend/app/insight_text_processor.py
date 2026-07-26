"""招聘经验文本清洗与去重"""

import hashlib
import re
from typing import List, Dict

MIN_BODY_LEN = 40
MAX_BODY_LEN = 12000

NOISE_PATTERNS = [
    re.compile(r"<[^>]+>"),
    re.compile(r"\[removed\]|\[deleted\]", re.I),
    re.compile(r"http[s]?://\S+"),
]


def clean_text(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    for pat in NOISE_PATTERNS:
        t = pat.sub(" ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()[:MAX_BODY_LEN]


def content_hash(title: str, body: str) -> str:
    raw = f"{title}|{body}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def dedupe_posts(posts: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for p in posts:
        body = clean_text(p.get("body", ""))
        title = clean_text(p.get("title", ""))
        if len(body) < MIN_BODY_LEN and len(title) < 15:
            continue
        h = content_hash(title, body)
        if h in seen:
            continue
        seen.add(h)
        p["title"] = title
        p["body"] = body
        p["content_hash"] = h
        out.append(p)
    return out


def is_hiring_related(text: str) -> bool:
    """过滤明显无关帖"""
    keywords = [
        "面试",
        "offer",
        "录用",
        "上岸",
        "入职",
        "校招",
        "社招",
        "简历",
        "hiring",
        "interview",
        "recruit",
        "job",
        "career",
        "salary",
        "岗位",
        "求职",
        "背调",
        "笔试",
        "复试",
        "hr",
    ]
    t = text.lower()
    return any(k in t for k in keywords)

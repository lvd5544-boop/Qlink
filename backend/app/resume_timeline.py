"""简历时间线抽取与日期工具（供 credibility / claim_reasoning 共用）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple


def parse_year_month(text: str) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    m = re.search(r"(\d{4})[.\-/年](\d{1,2})", str(text))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{4})", str(text))
    if m:
        return int(m.group(1)), 1
    return None


def months_between(start: Tuple[int, int], end: Tuple[int, int]) -> int:
    return (end[0] - start[0]) * 12 + (end[1] - start[1])


def overlap_months(
    a_start: Tuple[int, int],
    a_end: Tuple[int, int],
    b_start: Tuple[int, int],
    b_end: Tuple[int, int],
) -> int:
    start = max(a_start[0] * 12 + a_start[1], b_start[0] * 12 + b_start[1])
    end = min(a_end[0] * 12 + a_end[1], b_end[0] * 12 + b_end[1])
    return max(0, end - start)


def extract_timeline_events(resume_json: dict) -> List[dict]:
    """从 parsed_json 抽取时间线事件。"""
    events: List[dict] = []

    edu = resume_json.get("education")
    if isinstance(edu, list):
        for idx, e in enumerate(edu):
            if not isinstance(e, dict):
                continue
            start = parse_year_month(e.get("start_date") or e.get("duration") or "")
            end = parse_year_month(
                e.get("end_date") or e.get("graduation") or e.get("duration") or ""
            )
            events.append(
                {
                    "type": "education",
                    "index": idx,
                    "label": f"{e.get('school') or '院校'} · {e.get('degree') or '学历'}",
                    "start": start,
                    "end": end,
                    "study_type": e.get("study_type") or "未标注",
                    "raw": e,
                }
            )
    elif isinstance(edu, str) and edu:
        events.append(
            {
                "type": "education",
                "index": 0,
                "label": edu,
                "start": None,
                "end": None,
                "study_type": "未标注",
                "raw": {"education": edu},
            }
        )

    for idx, exp in enumerate(resume_json.get("work_experience") or []):
        if not isinstance(exp, dict):
            continue
        dur = exp.get("duration") or exp.get("period") or ""
        start = parse_year_month(exp.get("start_date") or dur)
        end = parse_year_month(exp.get("end_date") or dur)
        if not end and "至今" in str(dur):
            now = datetime.now()
            end = (now.year, now.month)
        events.append(
            {
                "type": "work",
                "index": idx,
                "label": f"{exp.get('company') or '公司'} · {exp.get('position') or exp.get('title') or '职位'}",
                "start": start,
                "end": end,
                "employment_type": exp.get("employment_type") or "全职",
                "description": exp.get("description") or "",
                "raw": exp,
            }
        )

    for idx, proj in enumerate(resume_json.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        dur = proj.get("duration") or proj.get("time_range") or ""
        start = parse_year_month(proj.get("start_date") or dur)
        end = parse_year_month(proj.get("end_date") or dur)
        events.append(
            {
                "type": "project",
                "index": idx,
                "label": f"项目 · {proj.get('name') or '未命名'}",
                "start": start,
                "end": end,
                "description": proj.get("description") or "",
                "raw": proj,
            }
        )

    return events


def estimate_work_years(events: List[dict]) -> float:
    total = 0
    for w in [e for e in events if e["type"] == "work" and e.get("start") and e.get("end")]:
        total += months_between(w["start"], w["end"])
    return round(total / 12, 1)

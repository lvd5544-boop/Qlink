"""
按 field_path 将建议写回简历 JSON。

field_path 示例：
  summary
  skills
  basic.name
  work_experience[0].description
  projects[1].description
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

FIELD_PATH_RE = re.compile(r"^(\w+)(?:\[(\d+)\])?(?:\.(\w+))?$")


def parse_field_path(field_path: str) -> Tuple[str, Optional[int], Optional[str]]:
    path = (field_path or "").strip()
    match = FIELD_PATH_RE.match(path)
    if not match:
        raise ValueError(f"无效的 field_path: {field_path}")
    section, index_str, field = match.groups()
    index = int(index_str) if index_str is not None else None
    return section, index, field


def patch_from_field_path(field_path: str, value: Any, action: str = "fill_field") -> dict:
    section, index, field = parse_field_path(field_path)
    patch: Dict[str, Any] = {
        "action": action,
        "section": section,
        "field_path": field_path,
        "value": value,
    }
    if index is not None:
        patch["index"] = index
    if field:
        patch["field"] = field
    if section == "summary" and not field:
        patch.pop("field", None)
    if section == "skills" and not field:
        patch.pop("field", None)
    return patch


def normalize_patch(patch: dict) -> dict:
    """将 field_path 规范化为 section/index/field 结构。"""
    data = dict(patch or {})
    field_path = data.get("field_path")
    if not field_path:
        return data
    section, index, field = parse_field_path(field_path)
    data.setdefault("section", section)
    if index is not None:
        data.setdefault("index", index)
    if field:
        data.setdefault("field", field)
    if section == "summary" and not field:
        data["section"] = "summary"
    if section == "skills" and not field:
        data["section"] = "skills"
    data.setdefault("action", "fill_field")
    return data


def apply_field_path(parsed_json: dict, field_path: str, value: Any) -> dict:
    from .resume_suggestions import apply_suggestion_patch

    patch = patch_from_field_path(field_path, value)
    return apply_suggestion_patch(parsed_json, patch)


def field_path_from_patch(patch: dict) -> Optional[str]:
    if patch.get("field_path"):
        return patch["field_path"]
    section = patch.get("section")
    if not section:
        return None
    index = patch.get("index")
    field = patch.get("field")
    if section == "summary":
        return "summary"
    if section == "skills":
        return "skills"
    if section == "basic" and field:
        return f"basic.{field}"
    if index is not None:
        fld = field or "description"
        return f"{section}[{index}].{fld}"
    if field:
        return f"{section}.{field}"
    return section

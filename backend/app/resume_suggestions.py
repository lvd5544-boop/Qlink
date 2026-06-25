"""
简历建议采纳：将优化建议应用到 parsed_json，并估算匹配分变化。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from .matching_hybrid import hybrid_score_v2
from .resume_apply import field_path_from_patch, normalize_patch, patch_from_field_path

QUANTIFICATION_TEMPLATES = [
    "通过技术优化将系统性能提升约 30%，核心接口 P99 延迟降低 40%",
    "负责模块日活用户达 10 万+，转化率较上线前提升 15%",
    "推动跨 3 个部门协作落地，项目周期缩短 20%，节省人力成本约 25%",
]


def _append_quantification_text(desc: str, index: int, custom_value: Optional[str] = None) -> str:
    template = custom_value or QUANTIFICATION_TEMPLATES[index % len(QUANTIFICATION_TEMPLATES)]
    desc = (desc or "").strip()
    if desc:
        return f"{desc}；{template}"
    return template


def preview_suggestion_patch(parsed_json: dict, patch: dict) -> dict:
    """预览建议采纳前后的文本，不修改简历。"""
    data = parsed_json or {}
    action = patch.get("action", "fill_field")
    section = patch.get("section", "basic")
    field = patch.get("field")
    index = patch.get("index")
    value = patch.get("value")

    if action == "add_project" and section == "projects":
        proj = value if isinstance(value, dict) else {}
        return {
            "original_text": "（暂无项目经历）",
            "suggested_text": (
                f"{proj.get('name', '')} · {proj.get('role', '')} · {proj.get('description', '')}".strip(" ·")
            ),
            "section_label": "项目经历",
        }

    if action == "append_quantification" and section in ("work_experience", "projects"):
        items = list(data.get(section) or [])
        if index is None or index < 0 or index >= len(items):
            raise ValueError(f"无效的{section}索引")
        item = items[index]
        name_key = "company" if section == "work_experience" else "name"
        section_label = "工作经历" if section == "work_experience" else "项目经历"
        original = (item.get("description") or "").strip() or "（暂无描述）"
        suggested = _append_quantification_text(
            original if original != "（暂无描述）" else "", index or 0, value
        )
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": f"{section_label} · {item.get(name_key) or '未命名'} · 描述",
        }

    if section == "projects" and index is not None:
        projs = data.get("projects") or []
        if index < 0 or index >= len(projs):
            raise ValueError("无效的项目经历索引")
        proj = projs[index]
        fld = field or "description"
        original = (proj.get(fld) or "").strip() or "（空）"
        suggested = str(value or "").strip() or original
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": f"项目经历 · {proj.get('name') or '未命名项目'} · {fld}",
        }

    if section == "work_experience" and index is not None:
        exps = data.get("work_experience") or []
        if index < 0 or index >= len(exps):
            raise ValueError("无效的工作经历索引")
        exp = exps[index]
        fld = field or "description"
        original = (exp.get(fld) or "").strip() or "（空）"
        suggested = str(value or "").strip() or original
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": f"工作经历 · {exp.get('company') or '未命名公司'} · {fld}",
        }

    if section == "summary":
        original = (data.get("summary") or "").strip() or "（空）"
        suggested = str(value or "").strip() or original
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": "个人简介",
        }

    if section == "skills":
        skills = data.get("skills") or []
        names = [
            (s.get("name") if isinstance(s, dict) else str(s))
            for s in skills
        ]
        original = "、".join(names) if names else "（暂无技能）"
        skill_name = str(value or "").strip()
        suggested = f"{original}、{skill_name}" if names else skill_name
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": "技能",
        }

    if section == "basic" and field:
        label_map = {
            "name": "姓名",
            "email": "邮箱",
            "phone": "电话",
            "expected_job_title": "期望职位",
            "location_preference": "期望地点",
            "education": "学历",
            "school": "院校",
            "degree": "学位",
        }
        original = (data.get(field) or "").strip() or "（空）"
        suggested = str(value or "").strip() or original
        return {
            "original_text": original,
            "suggested_text": suggested,
            "section_label": label_map.get(field, field),
        }

    raise ValueError("无法预览该建议")


def apply_suggestion_patch(parsed_json: dict, patch: dict) -> dict:
    """
    将建议补丁写入简历 JSON。

    patch 字段：
      - field_path: 如 work_experience[0].description（优先）
      - action: fill_field | update_work_exp | append_quantification | add_project
      - section: basic | work_experience | summary | skills | projects
      - field, index, value
    """
    data = copy.deepcopy(parsed_json or {})
    patch = normalize_patch(patch or {})
    action = patch.get("action", "fill_field")
    section = patch.get("section", "basic")
    field = patch.get("field")
    index = patch.get("index")
    value = patch.get("value")

    if action == "add_project" and section == "projects":
        proj = dict(value or {})
        if not (proj.get("name") or "").strip():
            raise ValueError("项目名称不能为空")
        projs = list(data.get("projects") or [])
        projs.append(proj)
        data["projects"] = projs
        return data

    if action == "append_quantification" and section in ("work_experience", "projects"):
        items = list(data.get(section) or [])
        if index is None or index < 0 or index >= len(items):
            raise ValueError(f"无效的{section}索引")
        item = dict(items[index])
        desc = (item.get("description") or "").strip()
        item["description"] = _append_quantification_text(desc, index or 0, value)
        items[index] = item
        data[section] = items
        return data

    if section == "projects" and index is not None:
        projs = list(data.get("projects") or [])
        if index < 0 or index >= len(projs):
            raise ValueError("无效的项目经历索引")
        proj = dict(projs[index])
        if field:
            proj[field] = value
        projs[index] = proj
        data["projects"] = projs
        return data

    if section == "work_experience" and index is not None:
        exps = list(data.get("work_experience") or [])
        if index < 0 or index >= len(exps):
            raise ValueError("无效的工作经历索引")
        exp = dict(exps[index])
        if field:
            exp[field] = value
        exps[index] = exp
        data["work_experience"] = exps
        return data

    if section == "summary":
        data["summary"] = value
        return data

    if section == "skills" and value:
        skills = list(data.get("skills") or [])
        skill_name = str(value).strip()
        if skill_name and not any(
            (s.get("name") if isinstance(s, dict) else str(s)) == skill_name for s in skills
        ):
            skills.append({"name": skill_name, "level": "intermediate"})
        data["skills"] = skills
        return data

    if section == "basic" and field:
        data[field] = value
        return data

    raise ValueError("无法识别的建议补丁")


def compute_match_score_delta(
    old_json: dict,
    new_json: dict,
    job_json: dict,
    job_title: str = "",
) -> Tuple[float, float, float]:
    """返回 (old_score, new_score, score_delta)。"""
    old_score, _, _, _ = hybrid_score_v2(old_json or {}, job_json or {}, job_title)
    new_score, _, _, _ = hybrid_score_v2(new_json or {}, job_json or {}, job_title)
    return old_score, new_score, round(new_score - old_score, 2)


def compute_suggestion_impact(
    old_json: dict,
    new_json: dict,
    job_json: Optional[dict] = None,
    job_title: str = "",
) -> dict:
    """计算建议采纳对体检分与匹配分的影响。"""
    from .resume_health import compute_resume_health

    health_old = compute_resume_health(old_json)
    health_new = compute_resume_health(new_json)

    result = {
        "health_old_score": health_old["overall_score"],
        "health_new_score": health_new["overall_score"],
        "health_score_delta": round(
            health_new["overall_score"] - health_old["overall_score"], 1
        ),
        "completeness_delta": round(
            health_new["completeness"]["score"] - health_old["completeness"]["score"], 1
        ),
        "quantification_delta": round(
            health_new["quantification"]["score"] - health_old["quantification"]["score"], 1
        ),
        "health_check_preview": health_new,
    }

    if job_json:
        old_match, new_match, match_delta = compute_match_score_delta(
            old_json, new_json, job_json, job_title
        )
        result.update({
            "old_score": old_match,
            "new_score": new_match,
            "score_delta": match_delta,
        })
    else:
        result.update({
            "old_score": None,
            "new_score": None,
            "score_delta": 0.0,
        })

    return result


def _enrich_suggestion(parsed_json: dict, base: dict) -> dict:
    """为建议附加原文/修改版预览与 field_path。"""
    item = dict(base)
    patch = dict(item.get("patch") or {})
    if not patch.get("field_path"):
        fp = field_path_from_patch(patch)
        if fp:
            patch["field_path"] = fp
    item["patch"] = patch
    try:
        preview = preview_suggestion_patch(parsed_json, patch)
        item["original_text"] = preview["original_text"]
        item["suggested_text"] = preview["suggested_text"]
        item["section_label"] = preview["section_label"]
    except ValueError:
        item["original_text"] = item.get("example_before") or ""
        item["suggested_text"] = item.get("example_after") or ""
        item["section_label"] = item.get("title", "")
    item["field_path"] = patch.get("field_path") or field_path_from_patch(patch)
    return item


SECTION_ALIASES = {
    "工作经历": "work_experience",
    "work_experience": "work_experience",
    "项目经历": "projects",
    "projects": "projects",
    "技能": "skills",
    "skills": "skills",
    "教育背景": "basic",
    "自我评价": "summary",
    "个人简介": "summary",
    "summary": "summary",
}


def _infer_field_path(resume_json: dict, suggestion: dict) -> Optional[str]:
    section_raw = suggestion.get("section") or ""
    section = SECTION_ALIASES.get(section_raw, section_raw)
    example_before = (suggestion.get("example_before") or "").strip()

    if section == "summary":
        return "summary"
    if section == "skills":
        return "skills"

    if section == "basic":
        for field in ("school", "degree", "education", "expected_job_title", "name"):
            if example_before and (resume_json.get(field) or "").strip() == example_before:
                return f"basic.{field}"
        return "basic.school"

    if section in ("work_experience", "projects"):
        items = resume_json.get(section) or []
        name_key = "company" if section == "work_experience" else "name"
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            desc = (item.get("description") or "").strip()
            if example_before and example_before in desc:
                return f"{section}[{idx}].description"
            if example_before and example_before == (item.get(name_key) or "").strip():
                return f"{section}[{idx}].description"
        if items:
            return f"{section}[0].description"

    explicit = suggestion.get("field_path")
    if explicit:
        return explicit
    return None


def coach_suggestion_to_actionable(
    parsed_json: dict,
    coach_item: dict,
    index: int,
    job_id: Optional[str] = None,
) -> Optional[dict]:
    """将 coach 单条建议转为可采纳的结构化建议。"""
    example_after = (coach_item.get("example_after") or "").strip()
    example_before = (coach_item.get("example_before") or "").strip()
    if not example_after and not coach_item.get("advice"):
        return None

    field_path = coach_item.get("field_path") or _infer_field_path(parsed_json, coach_item)
    if not field_path and not example_after:
        return None

    value = example_after or coach_item.get("advice", "")
    patch = normalize_patch(patch_from_field_path(field_path, value)) if field_path else {
        "action": "fill_field",
        "section": "summary",
        "value": value,
        "field_path": "summary",
    }

    base = {
        "id": f"coach_{index}",
        "source": "coach",
        "job_id": job_id,
        "title": coach_item.get("section") or "简历优化",
        "description": coach_item.get("issue") or coach_item.get("advice") or "",
        "priority": coach_item.get("priority") or "中",
        "issue": coach_item.get("issue"),
        "advice": coach_item.get("advice"),
        "example_before": example_before,
        "example_after": example_after,
        "field_path": patch.get("field_path"),
        "patch": patch,
    }
    return _enrich_suggestion(parsed_json, base)


def build_coach_actionable_suggestions(
    parsed_json: dict,
    coach_result: dict,
    job_id: Optional[str] = None,
) -> list[dict]:
    coach = (coach_result or {}).get("coach") or {}
    actions: list[dict] = []
    for idx, item in enumerate(coach.get("suggestions") or []):
        actionable = coach_suggestion_to_actionable(parsed_json, item, idx, job_id=job_id)
        if actionable:
            actions.append(actionable)
    return actions[:8]


def build_actionable_suggestions(parsed_json: dict, health_check: Optional[dict]) -> list[dict]:
    """从体检结果生成可对比预览、可采纳的结构化建议。"""
    actions: list[dict] = []
    data = parsed_json or {}
    health = health_check or {}

    for label in (health.get("completeness") or {}).get("missing") or []:
        field_map = {
            "姓名": ("basic", "name", "请填写您的姓名"),
            "邮箱": ("basic", "email", "example@email.com"),
            "电话": ("basic", "phone", "13800000000"),
            "期望职位": ("basic", "expected_job_title", "软件工程师"),
            "个人简介": ("summary", None, "具备 3 年相关经验，擅长核心业务开发，主导过关键项目并取得可量化成果（如性能提升 30%）。"),
            "期望地点": ("basic", "location_preference", "上海"),
            "学历": ("basic", "education", "本科"),
            "院校": ("basic", "school", "某某大学"),
            "学位": ("basic", "degree", "学士"),
            "项目经历": ("projects", None, None),
        }
        if label not in field_map:
            continue
        section, field, placeholder = field_map[label]
        if label == "项目经历":
            actions.append(_enrich_suggestion(data, {
                "id": "add_project_placeholder",
                "source": "health_check",
                "title": "补充项目经历",
                "description": "技术岗建议至少 1 个代表性项目",
                "priority": "高",
                "patch": {
                    "action": "add_project",
                    "section": "projects",
                    "value": {
                        "name": "电商订单系统重构",
                        "role": "核心开发",
                        "duration": "2023.01-2023.06",
                        "description": "负责订单模块重构，QPS 提升 40%，支撑日订单 10 万+",
                    },
                },
            }))
            continue
        actions.append(_enrich_suggestion(data, {
            "id": f"fill_{field or 'summary'}",
            "source": "health_check",
            "title": f"补充{label}",
            "description": f"当前缺少{label}，填写后可提升完整度",
            "priority": "高",
            "patch": {
                "action": "fill_field",
                "section": section,
                "field": field,
                "value": placeholder,
            },
        }))

    quant = health.get("quantification") or {}
    quantified_ids = set()
    for entry in quant.get("unquantified_entries") or []:
        entry_id = entry.get("id") or f"{entry.get('entry_type')}_{entry.get('index')}"
        details = quant.get("details") or []
        detail = next((d for d in details if d.get("id") == entry_id), {})
        if not detail:
            detail = next(
                (d for d in details
                 if d.get("entry_type") == entry.get("entry_type")
                 and d.get("index") == entry.get("index")),
                {},
            )
        name = detail.get("company") or "经历"
        section = "projects" if entry.get("entry_type") == "project" else "work_experience"
        sid = f"quantify_{entry_id}"
        quantified_ids.add(sid)
        actions.append(_enrich_suggestion(data, {
            "id": sid,
            "source": "health_check",
            "title": f"为「{name}」补充量化成果",
            "description": "建议补充数字、比例或规模，让成果更可验证",
            "priority": "高",
            "needs_followup": True,
            "entry_type": entry.get("entry_type"),
            "entry_index": entry.get("index"),
            "patch": {
                "action": "append_quantification",
                "section": section,
                "index": entry.get("index"),
            },
        }))

    # 兼容旧数据：仅有 unquantified_indices 时回退到工作经历
    if not quant.get("unquantified_entries"):
        for idx in quant.get("unquantified_indices") or []:
            details = quant.get("details") or []
            detail = next((d for d in details if d.get("index") == idx and d.get("entry_type") != "project"), {})
            company = detail.get("company") or f"经历 {idx + 1}"
            sid = f"quantify_work_{idx}"
            if sid in quantified_ids:
                continue
            actions.append(_enrich_suggestion(data, {
                "id": sid,
                "source": "health_check",
                "title": f"为「{company}」补充量化成果",
                "description": "建议补充数字、比例或规模，让成果更可验证",
                "priority": "高",
                "needs_followup": True,
                "entry_type": "work",
                "entry_index": idx,
                "patch": {
                    "action": "append_quantification",
                    "section": "work_experience",
                    "index": idx,
                },
            }))

    if not (data.get("skills") or []):
        actions.append(_enrich_suggestion(data, {
            "id": "add_skill_placeholder",
            "source": "health_check",
            "title": "添加核心技能",
            "description": "至少添加 1 项与目标岗位相关的技能",
            "priority": "中",
            "patch": {
                "action": "fill_field",
                "section": "skills",
                "value": "Python",
            },
        }))

    # 工作经历描述偏短但已有描述、未触发量化建议时，仍给出改写示例
    exps = data.get("work_experience") or []
    quantified_ids = {f"quantify_{i}" for i in (quant.get("unquantified_indices") or [])}
    for idx, exp in enumerate(exps):
        if not isinstance(exp, dict):
            continue
        sid = f"quantify_{idx}"
        if sid in quantified_ids:
            continue
        desc = (exp.get("description") or "").strip()
        if len(desc) < 20 and desc:
            actions.append(_enrich_suggestion(data, {
                "id": f"expand_{idx}",
                "source": "health_check",
                "title": f"丰富「{exp.get('company') or f'经历 {idx + 1}'}」描述",
                "description": "描述较短，可补充职责范围与量化成果",
                "priority": "中",
                "needs_followup": True,
                "entry_type": "work",
                "entry_index": idx,
                "patch": {
                    "action": "append_quantification",
                    "section": "work_experience",
                    "index": idx,
                },
            }))

    return actions[:10]

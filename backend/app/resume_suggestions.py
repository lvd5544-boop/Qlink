"""
简历建议采纳：将优化建议应用到 parsed_json，并估算匹配分变化。
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional, Tuple

from .matching_hybrid import hybrid_score_v2
from .resume_apply import field_path_from_patch, normalize_patch, patch_from_field_path

# 占位 / 未完成追问文案：不得写入简历
_PLACEHOLDER_PATTERNS = (
    re.compile(r"需先完成"),
    re.compile(r"待补充"),
    re.compile(r"待填写"),
    re.compile(r"请先完成"),
    re.compile(r"填入真实数据后再"),
    re.compile(r"^（?\s*空\s*）?$"),
    re.compile(r"^N/?A$", re.I),
    re.compile(r"^TODO$", re.I),
    re.compile(r"^TBD$", re.I),
)

_PLACEHOLDER_EXACT = {
    "",
    "（空）",
    "(空)",
    "（暂无描述）",
    "（暂无技能）",
    "（需先完成证据追问，填入真实数据后再预览改写）",
}


def is_placeholder_value(value: Any) -> bool:
    """判断补丁值是否为占位文案或空值。"""
    if value is None:
        return True
    if isinstance(value, dict):
        # add_project 等：检查 description
        return is_placeholder_value(value.get("description"))
    text = str(value).strip()
    if text in _PLACEHOLDER_EXACT:
        return True
    return any(p.search(text) for p in _PLACEHOLDER_PATTERNS)


def reject_if_placeholder(value: Any, *, context: str = "建议内容") -> None:
    if is_placeholder_value(value):
        raise ValueError(
            f"{context}不能为空或占位文案（如「需先完成证据追问」「待补充」）。"
            "请先完成证据追问后再采纳。"
        )


def validate_client_patch_against_stored(
    client_patch: dict,
    stored: Optional[dict],
    *,
    evidence_completed: bool = False,
) -> dict:
    """
    以数据库中的 suggestion 为准校验客户端 patch。
    - 不得把 append_quantification 改成 fill_field 绕过护栏
    - requires_evidence 未完成时拒绝应用
    返回最终应使用的 patch（优先 stored）。
    """
    client = normalize_patch(client_patch or {})
    if not stored:
        reject_if_placeholder(client.get("value"), context="补丁内容")
        return client

    stored_patch = normalize_patch(stored.get("patch") or {})
    stored_action = stored_patch.get("action") or "fill_field"
    client_action = client.get("action") or stored_action

    if client_action != stored_action:
        raise ValueError(
            f"补丁 action 与存储建议不一致（期望 {stored_action}，收到 {client_action}）。"
            "禁止将 append_quantification 改为 fill_field。"
        )

    for key in ("section", "index", "field"):
        stored_val = stored_patch.get(key)
        client_val = client.get(key)
        if stored_val is not None and client_val is not None and stored_val != client_val:
            raise ValueError(f"补丁字段 {key} 与存储建议不一致")

    requires_evidence = bool(
        stored.get("requires_evidence")
        or stored.get("needs_followup")
        or stored_action == "append_quantification"
    )
    if requires_evidence and not evidence_completed:
        # 允许：stored 为 append，且客户端提供了非占位的真实 value（已完成追问后的证据）
        value = client.get("value")
        if is_placeholder_value(value):
            raise ValueError("该建议需要先完成证据追问。未提供真实证据前不能写回简历。")
        # 有真实 value 时仍强制走 stored action（通常是 append_quantification）
        merged = dict(stored_patch)
        merged["value"] = value
        for key in (
            "evidence_completed",
            "evidence_references",
            "fidelity_result",
            "fidelity_proof",
        ):
            if client.get(key) is not None:
                merged[key] = client.get(key)
        reject_if_placeholder(merged.get("value"))
        return merged

    # 无证据要求：以存储 patch 为主，允许客户端覆盖 value（编辑后采纳）
    merged = dict(stored_patch)
    if client.get("value") is not None:
        merged["value"] = client.get("value")
    for key in (
        "evidence_completed",
        "evidence_references",
        "fidelity_result",
        "fidelity_proof",
    ):
        if client.get(key) is not None:
            merged[key] = client.get(key)
    reject_if_placeholder(merged.get("value"), context="补丁内容")
    return merged


def _append_quantification_text(desc: str, index: int, custom_value: Optional[str] = None) -> str:
    """
    仅拼接用户/忠实扩写提供的证据文本。
    禁止注入虚构量化模板（与「忠实扩写」品牌一致）。
    """
    evidence = (custom_value or "").strip()
    if not evidence:
        raise ValueError(
            "补充量化必须基于您提供的真实数据。请先完成「AI 证据追问 / 忠实扩写」后再采纳。"
        )
    reject_if_placeholder(evidence, context="量化证据")
    desc = (desc or "").strip()
    if desc:
        return f"{desc}；{evidence}"
    return evidence


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
                f"{proj.get('name', '')} · {proj.get('role', '')} · {proj.get('description', '')}".strip(
                    " ·"
                )
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
        if value and str(value).strip():
            suggested = _append_quantification_text(
                original if original != "（暂无描述）" else "", index or 0, value
            )
        else:
            suggested = "（需先完成证据追问，填入真实数据后再预览改写）"
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
        names = [(s.get("name") if isinstance(s, dict) else str(s)) for s in skills]
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

    对 fill_field / append_quantification 均拒绝占位文案；fill_field 不能成为
    绕过 append_quantification 证据护栏的通道。
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
        reject_if_placeholder(proj.get("description"), context="项目描述")
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

    # fill_field 及同类写回：拒绝占位文案
    if action in ("fill_field", "update_work_exp") or section in (
        "projects",
        "work_experience",
        "summary",
        "skills",
        "basic",
    ):
        if section in ("projects", "work_experience", "summary") or (section == "basic" and field):
            reject_if_placeholder(value, context="写回内容")

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
        reject_if_placeholder(value, context="技能名称")
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
        "health_score_delta": round(health_new["overall_score"] - health_old["overall_score"], 1),
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
        result.update(
            {
                "old_score": old_match,
                "new_score": new_match,
                "score_delta": match_delta,
            }
        )
    else:
        result.update(
            {
                "old_score": None,
                "new_score": None,
                "score_delta": 0.0,
            }
        )

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
    patch = (
        normalize_patch(patch_from_field_path(field_path, value))
        if field_path
        else {
            "action": "fill_field",
            "section": "summary",
            "value": value,
            "field_path": "summary",
        }
    )

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


def build_consistency_actionable_suggestions(
    parsed_json: dict,
    health_check: Optional[dict],
) -> list[dict]:
    """将表述一致性诊断转为可预览、可采纳的改稿建议。"""
    diag = (health_check or {}).get("consistency_diagnosis") or {}
    actions: list[dict] = []
    for item in diag.get("issues") or []:
        patch = item.get("patch")
        if not patch:
            continue
        try:
            preview = preview_suggestion_patch(parsed_json, patch)
        except ValueError:
            preview = {
                "original_text": item.get("detected", ""),
                "suggested_text": item.get("example_rewrite", ""),
                "section_label": item.get("field_path", ""),
            }
        actions.append(
            _enrich_suggestion(
                parsed_json,
                {
                    "id": f"consistency_{item['id']}",
                    "source": "consistency",
                    "title": item.get("title"),
                    "description": item.get("wording_fix"),
                    "priority": "高" if item.get("severity") == "medium" else "中",
                    "issue": item.get("why"),
                    "advice": item.get("wording_fix"),
                    "example_before": preview.get("original_text") or item.get("detected"),
                    "example_after": preview.get("suggested_text") or item.get("example_rewrite"),
                    "field_path": item.get("field_path"),
                    "needs_followup": item.get("entry_type") in ("work", "project"),
                    "entry_type": item.get("entry_type"),
                    "entry_index": item.get("entry_index"),
                    "patch": patch,
                },
            )
        )
    return actions[:6]


def build_actionable_suggestions(parsed_json: dict, health_check: Optional[dict]) -> list[dict]:
    """从体检结果生成可对比预览、可采纳的结构化建议。"""
    actions: list[dict] = []
    data = parsed_json or {}
    health = health_check or {}

    actions.extend(build_consistency_actionable_suggestions(data, health))

    for label in (health.get("completeness") or {}).get("missing") or []:
        field_map = {
            "姓名": ("basic", "name", "请填写您的姓名"),
            "邮箱": ("basic", "email", "example@email.com"),
            "电话": ("basic", "phone", "13800000000"),
            "期望职位": ("basic", "expected_job_title", "软件工程师"),
            "个人简介": (
                "summary",
                None,
                "具备相关经验，擅长核心业务开发，主导过关键项目并取得可验证成果。",
            ),
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
            actions.append(
                _enrich_suggestion(
                    data,
                    {
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
                                "description": "负责订单模块重构，请补充您真实的规模与结果数据",
                            },
                        },
                    },
                )
            )
            continue
        actions.append(
            _enrich_suggestion(
                data,
                {
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
                },
            )
        )

    quant = health.get("quantification") or {}
    quantified_ids = set()
    for entry in quant.get("unquantified_entries") or []:
        entry_id = entry.get("id") or f"{entry.get('entry_type')}_{entry.get('index')}"
        details = quant.get("details") or []
        detail = next((d for d in details if d.get("id") == entry_id), {})
        if not detail:
            detail = next(
                (
                    d
                    for d in details
                    if d.get("entry_type") == entry.get("entry_type")
                    and d.get("index") == entry.get("index")
                ),
                {},
            )
        name = detail.get("company") or "经历"
        section = "projects" if entry.get("entry_type") == "project" else "work_experience"
        sid = f"quantify_{entry_id}"
        quantified_ids.add(sid)
        actions.append(
            _enrich_suggestion(
                data,
                {
                    "id": sid,
                    "source": "health_check",
                    "title": f"为「{name}」补充量化成果",
                    "description": "请通过「证据追问」补充真实数字后再改写，不会自动填入虚构指标",
                    "priority": "高",
                    "needs_followup": True,
                    "requires_evidence": True,
                    "entry_type": entry.get("entry_type"),
                    "entry_index": entry.get("index"),
                    "patch": {
                        # value 必须由证据追问生成；无 value 时 apply 会拒绝
                        "action": "append_quantification",
                        "section": section,
                        "index": entry.get("index"),
                        "value": None,
                    },
                },
            )
        )

    # 兼容旧数据：仅有 unquantified_indices 时回退到工作经历
    if not quant.get("unquantified_entries"):
        for idx in quant.get("unquantified_indices") or []:
            details = quant.get("details") or []
            detail = next(
                (d for d in details if d.get("index") == idx and d.get("entry_type") != "project"),
                {},
            )
            company = detail.get("company") or f"经历 {idx + 1}"
            sid = f"quantify_work_{idx}"
            if sid in quantified_ids:
                continue
            actions.append(
                _enrich_suggestion(
                    data,
                    {
                        "id": sid,
                        "source": "health_check",
                        "title": f"为「{company}」补充量化成果",
                        "description": "请通过「证据追问」补充真实数字后再改写，不会自动填入虚构指标",
                        "priority": "高",
                        "needs_followup": True,
                        "requires_evidence": True,
                        "entry_type": "work",
                        "entry_index": idx,
                        "patch": {
                            "action": "append_quantification",
                            "section": "work_experience",
                            "index": idx,
                            "value": None,
                        },
                    },
                )
            )

    if not (data.get("skills") or []):
        actions.append(
            _enrich_suggestion(
                data,
                {
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
                },
            )
        )

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
            actions.append(
                _enrich_suggestion(
                    data,
                    {
                        "id": f"expand_{idx}",
                        "source": "health_check",
                        "title": f"丰富「{exp.get('company') or f'经历 {idx + 1}'}」描述",
                        "description": "描述较短，请通过证据追问补充真实职责与成果后再改写",
                        "priority": "中",
                        "needs_followup": True,
                        "requires_evidence": True,
                        "entry_type": "work",
                        "entry_index": idx,
                        "patch": {
                            "action": "append_quantification",
                            "section": "work_experience",
                            "index": idx,
                            "value": None,
                        },
                    },
                )
            )

    return actions[:12]

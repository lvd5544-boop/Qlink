"""
简历体检：完整度 + 经历量化检测（规则层，无 LLM）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .resume_consistency import diagnose_resume_consistency

# 完整度检测字段：(字段路径, 权重, 中文标签)
_COMPLETENESS_CHECKS: List[tuple[str, int, str]] = [
    ("name", 10, "姓名"),
    ("email", 8, "邮箱"),
    ("phone", 8, "电话"),
    ("expected_job_title", 12, "期望职位"),
    ("summary", 10, "个人简介"),
    ("skills", 12, "技能"),
    ("work_experience", 15, "工作经历"),
    ("projects", 8, "项目经历"),
    ("education", 8, "学历"),
    ("school", 5, "院校"),
    ("degree", 5, "学位"),
    ("location_preference", 7, "期望地点"),
]

_QUANT_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?"),  # 数字，含小数
    re.compile(r"%|％"),  # 百分号
    re.compile(r"百分之"),  # 中文百分比
    re.compile(r"[万亿千百]+"),  # 中文数量级
]


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _field_value(parsed_json: dict, field: str) -> Any:
    if field == "skills":
        skills = parsed_json.get("skills") or []
        return [s for s in skills if (s.get("name") if isinstance(s, dict) else str(s)).strip()]
    if field == "work_experience":
        exps = parsed_json.get("work_experience") or []
        return [
            e
            for e in exps
            if isinstance(e, dict)
            and (e.get("company") or "").strip()
            and (e.get("position") or "").strip()
        ]
    if field == "projects":
        projs = parsed_json.get("projects") or []
        return [p for p in projs if isinstance(p, dict) and (p.get("name") or "").strip()]
    return parsed_json.get(field)


def _check_completeness(parsed_json: dict) -> dict:
    total_weight = sum(w for _, w, _ in _COMPLETENESS_CHECKS)
    earned = 0
    missing: List[str] = []
    fields: Dict[str, dict] = {}

    for field, weight, label in _COMPLETENESS_CHECKS:
        value = _field_value(parsed_json, field)
        filled = _is_filled(value)
        if filled:
            earned += weight
        else:
            missing.append(label)
        fields[field] = {"label": label, "filled": filled, "weight": weight}

    # 工作经历描述完整度（附加项，不计入 missing 列表主字段）
    exps = parsed_json.get("work_experience") or []
    described = sum(1 for e in exps if isinstance(e, dict) and (e.get("description") or "").strip())
    exp_count = len(exps)
    description_ratio = (described / exp_count) if exp_count else 0.0

    score = round(earned / total_weight * 100) if total_weight else 0
    return {
        "score": score,
        "filled_weight": earned,
        "total_weight": total_weight,
        "missing": missing,
        "fields": fields,
        "work_experience_count": exp_count,
        "work_experience_with_description": described,
        "description_ratio": round(description_ratio, 2),
    }


def _description_has_quantification(description: str) -> bool:
    text = (description or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in _QUANT_PATTERNS)


def _check_quantification(parsed_json: dict) -> dict:
    details: List[dict] = []
    quantified_count = 0

    for idx, exp in enumerate(parsed_json.get("work_experience") or []):
        if not isinstance(exp, dict):
            continue
        desc = exp.get("description") or ""
        has_quant = _description_has_quantification(desc)
        if has_quant:
            quantified_count += 1
        details.append(
            {
                "id": f"work_{idx}",
                "index": idx,
                "entry_type": "work",
                "company": exp.get("company") or "",
                "position": exp.get("position") or "",
                "has_quantification": has_quant,
                "description_preview": desc[:120] if desc else "",
            }
        )

    for idx, proj in enumerate(parsed_json.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        desc = proj.get("description") or ""
        has_quant = _description_has_quantification(desc)
        if has_quant:
            quantified_count += 1
        details.append(
            {
                "id": f"project_{idx}",
                "index": idx,
                "entry_type": "project",
                "company": proj.get("name") or "",
                "position": proj.get("role") or "项目",
                "has_quantification": has_quant,
                "description_preview": desc[:120] if desc else "",
            }
        )

    total = len(details)
    score = round(quantified_count / total * 100) if total else 0
    unquantified_entries = [
        {"id": d["id"], "entry_type": d["entry_type"], "index": d["index"]}
        for d in details
        if not d["has_quantification"]
    ]

    return {
        "score": score,
        "total_experiences": total,
        "quantified_count": quantified_count,
        "unquantified_indices": [e["index"] for e in unquantified_entries],
        "unquantified_entries": unquantified_entries,
        "details": details,
    }


def _build_completeness_detail(completeness: dict) -> dict:
    """完整度评分明细：优势与不足。"""
    strengths: List[dict] = []
    weaknesses: List[dict] = []

    for info in completeness.get("fields", {}).values():
        label = info.get("label", "")
        if info.get("filled"):
            strengths.append(
                {
                    "title": label,
                    "detail": "已填写，计入完整度",
                }
            )
        else:
            weaknesses.append(
                {
                    "title": label,
                    "detail": "未填写，建议补充",
                }
            )

    exp_count = completeness.get("work_experience_count", 0)
    described = completeness.get("work_experience_with_description", 0)
    if exp_count > 0:
        if described == exp_count:
            strengths.append(
                {
                    "title": "工作经历描述",
                    "detail": f"全部 {exp_count} 段经历均有职责/成果描述",
                }
            )
        else:
            weaknesses.append(
                {
                    "title": "工作经历描述",
                    "detail": f"仅 {described}/{exp_count} 段经历有描述，其余偏空",
                }
            )

    return {
        "score": completeness.get("score", 0),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "summary": (f"已覆盖 {len(strengths)} 项关键字段" if strengths else "关键字段大多未填写"),
    }


def _build_overall_detail(
    completeness: dict,
    quantification: dict,
    overall_score: int,
) -> dict:
    """综合得分明细：优势与不足。"""
    strengths: List[dict] = []
    weaknesses: List[dict] = []

    comp_score = completeness.get("score", 0)
    quant_score = quantification.get("score", 0)

    if comp_score >= 70:
        strengths.append(
            {
                "title": "结构覆盖较好",
                "detail": f"完整度 {comp_score}%，主要模块填写齐全",
            }
        )
    elif comp_score >= 40:
        weaknesses.append(
            {
                "title": "结构覆盖一般",
                "detail": f"完整度 {comp_score}%，仍有较多字段待补充",
            }
        )
    else:
        weaknesses.append(
            {
                "title": "结构覆盖不足",
                "detail": f"完整度仅 {comp_score}%，是综合分主要短板",
            }
        )

    quant_total = quantification.get("total_experiences", 0)
    quant_ok = quantification.get("quantified_count", 0)
    if quant_score >= 60:
        strengths.append(
            {
                "title": "成果量化到位",
                "detail": f"{quant_ok}/{quant_total} 段经历含数字、比例等可验证成果",
            }
        )
    elif quant_total == 0:
        weaknesses.append(
            {
                "title": "缺少工作经历",
                "detail": "无经历则量化分为 0，建议补充并写上量化指标",
            }
        )
    else:
        weaknesses.append(
            {
                "title": "成果量化不足",
                "detail": f"仅 {quant_ok}/{quant_total} 段经历有量化描述，拉低综合分",
            }
        )

    for item in quantification.get("details") or []:
        company = item.get("company") or f"经历 {item.get('index', 0) + 1}"
        if item.get("has_quantification"):
            strengths.append(
                {
                    "title": company,
                    "detail": "描述含量化成果，有助于提升匹配说服力",
                }
            )
        elif (item.get("description_preview") or "").strip():
            weaknesses.append(
                {
                    "title": company,
                    "detail": "描述偏笼统，建议补充指标、规模或提升比例",
                }
            )

    filled_labels = [
        info.get("label") for info in completeness.get("fields", {}).values() if info.get("filled")
    ]
    if len(filled_labels) >= 6:
        strengths.append(
            {
                "title": "基础信息较完整",
                "detail": f"已填写：{'、'.join(filled_labels[:6])}{' 等' if len(filled_labels) > 6 else ''}",
            }
        )

    missing = completeness.get("missing") or []
    if missing:
        weaknesses.append(
            {
                "title": "待补关键字段",
                "detail": "、".join(missing[:6]) + (" 等" if len(missing) > 6 else ""),
            }
        )

    return {
        "score": overall_score,
        "formula": "综合得分 = 完整度 × 60% + 量化程度 × 40%",
        "strengths": strengths,
        "weaknesses": weaknesses,
        "summary": (
            f"当前综合 {overall_score} 分（完整度 {comp_score} 占 60%，量化 {quant_score} 占 40%）"
        ),
    }


def _build_suggestions(completeness: dict, quantification: dict) -> List[str]:
    suggestions: List[str] = []
    if completeness.get("missing"):
        top = completeness["missing"][:3]
        suggestions.append(f"建议补充：{'、'.join(top)}")

    if completeness.get("work_experience_count", 0) > 0:
        ratio = completeness.get("description_ratio", 0)
        if ratio < 1:
            suggestions.append("部分工作经历缺少描述，请补充职责与成果")

    unquantified = quantification.get("unquantified_indices") or []
    if unquantified:
        suggestions.append(
            f"有 {len(unquantified)} 段经历缺少量化成果，建议加入数字、比例或规模（如提升 30%、服务 10 万用户）"
        )
    elif quantification.get("total_experiences", 0) == 0:
        suggestions.append("添加工作经历并附上可量化的成果描述")

    if not suggestions:
        suggestions.append("简历结构较完整，可继续优化关键词与岗位匹配度")

    return suggestions


def compute_resume_health(parsed_json: Optional[dict]) -> dict:
    """对 parsed_json 做规则体检，返回可序列化结果。"""
    data = parsed_json or {}
    completeness = _check_completeness(data)
    quantification = _check_quantification(data)
    consistency = diagnose_resume_consistency(data)

    overall = round(completeness["score"] * 0.6 + quantification["score"] * 0.4)

    return {
        "overall_score": overall,
        "completeness": completeness,
        "quantification": quantification,
        "consistency_diagnosis": consistency,
        "overall_detail": _build_overall_detail(completeness, quantification, overall),
        "completeness_detail": _build_completeness_detail(completeness),
        "suggestions": _build_suggestions(completeness, quantification),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

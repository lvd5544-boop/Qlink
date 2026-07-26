"""
Claim 级履历推理审计：从整段风险报告升级为逐条 claim 推理。
产品原则：不判定真假，只标识不一致、不清晰、缺证据、需追问的 claim。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .audit_scoring import STATUS_LABELS, compute_risk_score
from .faithful_expansion import detect_template_phrases
from .resume_text import split_bullets
from .resume_timeline import (
    estimate_work_years,
    extract_timeline_events,
    overlap_months,
)

DISCLAIMER = (
    "本报告仅用于履历一致性与可验证性审查，不构成造假判定。"
    "最终结论需结合面试、候选人说明、证明材料与正式背调。"
)

DO_NOT_CONCLUDE = "不能据此判断造假，只能建议进一步核实与追问。"

_LEADERSHIP_WORDS = ("主导", "负责", "带领", "牵头", "统筹", "从0到1", "从 0 到 1")
_TECH_KEYWORDS = (
    "Redis",
    "Kafka",
    "MySQL",
    "PostgreSQL",
    "MongoDB",
    "Elasticsearch",
    "K8s",
    "Kubernetes",
    "Docker",
    "微服务",
    "分库分表",
    "消息队列",
    "Spring",
    "Vue",
    "React",
    "Python",
    "Java",
    "Go",
    "Rust",
)
_HIGH_PCT = re.compile(r"(提升|增长|降低|减少|优化|提高).{0,8}(\d{2,3}%|百分之[八九九十百])")
_TEAM_SIZE = re.compile(r"(\d+)\s*人")
_SENIOR_TITLES = ("总监", "VP", "副总裁", "负责人", "CTO", "CEO", "总经理", "架构师")


def _claim_id(section: str, entry_index: int, claim_type: str, seq: int) -> str:
    return f"{section}_{entry_index}_{claim_type}_{seq}"


def _classify_bullet(bullet: str, *, check_tech: bool = False) -> str:
    claim_type = "result" if _HIGH_PCT.search(bullet) or re.search(r"\d+", bullet) else "action"
    if any(w in bullet for w in _LEADERSHIP_WORDS):
        claim_type = "role"
    if check_tech and claim_type == "action":
        tech_hits = [k for k in _TECH_KEYWORDS if k.lower() in bullet.lower()]
        if len(tech_hits) >= 3:
            claim_type = "skill"
    return claim_type


def _append_entry_claims(
    claims: List[dict],
    *,
    section: str,
    idx: int,
    title: str,
    title_as: str,
    duration: str,
    company_or_project: str,
    position_or_role: str,
    description: str,
    check_tech: bool = False,
) -> None:
    if title:
        claims.append(
            {
                "id": _claim_id(section, idx, title_as, 0),
                "section": section,
                "entry_index": idx,
                "claim_type": title_as,
                "text": title,
                "source_text": title,
                "company_or_project": company_or_project,
                "position_or_role": position_or_role,
            }
        )
    if duration:
        claims.append(
            {
                "id": _claim_id(section, idx, "time", 0),
                "section": section,
                "entry_index": idx,
                "claim_type": "time",
                "text": duration,
                "source_text": duration,
                "company_or_project": company_or_project,
                "position_or_role": position_or_role,
            }
        )
    for seq, bullet in enumerate(split_bullets(description)):
        claim_type = _classify_bullet(bullet, check_tech=check_tech)
        claims.append(
            {
                "id": _claim_id(section, idx, claim_type, seq),
                "section": section,
                "entry_index": idx,
                "claim_type": claim_type,
                "text": bullet,
                "source_text": bullet,
                "company_or_project": company_or_project,
                "position_or_role": position_or_role,
            }
        )


def extract_resume_claims(resume_json: dict) -> List[dict]:
    """从简历 JSON 抽取 claim 列表。"""
    claims: List[dict] = []
    resume_json = resume_json or {}

    for idx, exp in enumerate(resume_json.get("work_experience") or []):
        if not isinstance(exp, dict):
            continue
        company = (exp.get("company") or "").strip()
        position = (exp.get("position") or exp.get("title") or "").strip()
        _append_entry_claims(
            claims,
            section="work_experience",
            idx=idx,
            title=position,
            title_as="title",
            duration=(exp.get("duration") or exp.get("period") or ""),
            company_or_project=company,
            position_or_role=position,
            description=(exp.get("description") or "").strip(),
        )

    for idx, proj in enumerate(resume_json.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        name = (proj.get("name") or "").strip()
        role = (proj.get("role") or proj.get("position") or "").strip()
        _append_entry_claims(
            claims,
            section="projects",
            idx=idx,
            title=name,
            title_as="title",
            duration=(proj.get("duration") or proj.get("time_range") or ""),
            company_or_project=name,
            position_or_role=role,
            description=(proj.get("description") or "").strip(),
            check_tech=True,
        )

    edu = resume_json.get("education")
    if isinstance(edu, list):
        for idx, e in enumerate(edu):
            if not isinstance(e, dict):
                continue
            school = (e.get("school") or "").strip()
            degree = (e.get("degree") or "").strip()
            if school or degree:
                claims.append(
                    {
                        "id": _claim_id("education", idx, "title", 0),
                        "section": "education",
                        "entry_index": idx,
                        "claim_type": "title",
                        "text": f"{school} · {degree}".strip(" ·"),
                        "source_text": f"{school} {degree}",
                        "company_or_project": school,
                        "position_or_role": degree,
                    }
                )

    for idx, skill in enumerate(resume_json.get("skills") or []):
        name = skill.get("name") if isinstance(skill, dict) else str(skill)
        name = (name or "").strip()
        if name:
            claims.append(
                {
                    "id": _claim_id("skills", idx, "skill", 0),
                    "section": "skills",
                    "entry_index": idx,
                    "claim_type": "skill",
                    "text": name,
                    "source_text": name,
                    "company_or_project": "",
                    "position_or_role": "",
                }
            )

    return claims


def _build_claim_item(
    claim: dict,
    risk_level: str,
    reasoning_chain: List[str],
    possible_explanations: List[str],
    verification_questions: List[str],
    evidence_suggestions: Optional[List[str]] = None,
) -> dict:
    return {
        "claim_id": claim["id"],
        "claim_type": claim["claim_type"],
        "claim_text": claim["text"],
        "source_section": claim["section"],
        "entry_index": claim["entry_index"],
        "risk_level": risk_level,
        "reasoning_chain": reasoning_chain,
        "possible_explanations": possible_explanations,
        "verification_questions": verification_questions,
        "evidence_suggestions": evidence_suggestions or [],
        "do_not_conclude": DO_NOT_CONCLUDE,
    }


def _reason_timeline_claims(claims: List[dict], events: List[dict]) -> List[dict]:
    """时间线冲突、项目不在职期间。"""
    items: List[dict] = []
    works = [e for e in events if e["type"] == "work" and e.get("start") and e.get("end")]
    projects_ev = [e for e in events if e["type"] == "project"]

    for i, w1 in enumerate(works):
        for w2 in works[i + 1 :]:
            if w1.get("employment_type") != "全职" or w2.get("employment_type") != "全职":
                continue
            ov = overlap_months(w1["start"], w1["end"], w2["start"], w2["end"])
            if ov > 1:
                for c in claims:
                    if c["section"] == "work_experience" and c["claim_type"] == "time":
                        if c["entry_index"] in (w1["index"], w2["index"]):
                            items.append(
                                _build_claim_item(
                                    c,
                                    "high" if ov > 3 else "medium",
                                    [
                                        f"两段全职经历重叠约 {ov} 个月",
                                        "简历未说明是否存在兼职/远程或日期笔误",
                                    ],
                                    [
                                        "其中一段可能为兼职或远程",
                                        "日期填写可能存在笔误",
                                    ],
                                    [
                                        "这两段经历是否存在时间重叠？若有，请说明工作形态。",
                                        "能否提供在职证明或劳动合同时间？",
                                    ],
                                    ["在职证明", "劳动合同截图"],
                                )
                            )

    for proj_ev in projects_ev:
        in_range = False
        for w in works:
            if proj_ev.get("start") and w.get("start") and w.get("end"):
                if (
                    overlap_months(
                        proj_ev["start"],
                        proj_ev["end"] or proj_ev["start"],
                        w["start"],
                        w["end"],
                    )
                    > 0
                ):
                    in_range = True
                    break
        if works and proj_ev.get("start") and not in_range:
            for c in claims:
                if (
                    c["section"] == "projects"
                    and c["entry_index"] == proj_ev["index"]
                    and c["claim_type"] == "time"
                ):
                    items.append(
                        _build_claim_item(
                            c,
                            "medium",
                            ["项目时间不在任何一段工作经历区间内", "需确认项目发生场景"],
                            ["可能是实习/独立/外包项目", "可能工作经历日期填写不完整"],
                            [f"「{c.get('company_or_project')}」是在哪家公司任职期间完成的？"],
                            ["项目合同或交付证明"],
                        )
                    )
    return items


def _reason_seniority_claims(
    claims: List[dict], resume_json: dict, events: List[dict]
) -> List[dict]:
    items: List[dict] = []
    years = estimate_work_years(events)

    for c in claims:
        if c["claim_type"] != "title" or c["section"] != "work_experience":
            continue
        title = c["text"]
        if years < 2 and any(t in title for t in _SENIOR_TITLES):
            items.append(
                _build_claim_item(
                    c,
                    "medium",
                    [f"工作年限约 {years} 年，但职位含高级头衔", "职级与年限存在不匹配信号"],
                    ["可能是创业公司扁平职级", "可能是虚线/代理头衔"],
                    ["该职位的汇报对象是谁？", "您直接管理多少人？决策范围是什么？"],
                    ["组织架构说明", "直属负责人证明"],
                )
            )

    for c in claims:
        if c["claim_type"] not in ("action", "role"):
            continue
        m = _TEAM_SIZE.search(c["text"])
        if m and years < 3:
            n = int(m.group(1))
            if n >= 20:
                items.append(
                    _build_claim_item(
                        c,
                        "medium",
                        [f"声称管理 {n} 人，但工作年限约 {years} 年", "管理规模与年限不匹配"],
                        ["可能含虚线/矩阵汇报", "可能是项目组成员而非直接下属"],
                        [f"管理 {n} 人是直接汇报还是含虚线？", "您的具体管理职责是什么？"],
                        ["组织架构图", "HR 证明"],
                    )
                )
    return items


def _reason_role_boundary_claims(claims: List[dict]) -> List[dict]:
    items: List[dict] = []
    builder_context = ("平台", "系统", "产品", "从0到1", "从 0 到 1", "全栈", "自研")
    for c in claims:
        if c["claim_type"] not in ("action", "role"):
            continue
        text = c["text"]
        lead_hits = [w for w in _LEADERSHIP_WORDS if w in text]
        if not lead_hits:
            continue
        # 创业/自研平台场景：负责产品+开发较常见，降低敏感度
        if any(k in text for k in builder_context) and len(text) >= 24:
            continue
        has_boundary = any(
            k in text
            for k in ("决策", "设计", "执行", "模块", "接口", "方案", "团队", "开发", "实现")
        )
        if not has_boundary or len(text) < 20:
            items.append(
                _build_claim_item(
                    c,
                    "low",
                    [
                        f"claim 含「{'/'.join(lead_hits[:2])}」但角色边界可更清晰",
                        "属于表述优化范畴，不一定是经历不实",
                    ],
                    ["候选人可能兼做产品与研发", "可能是团队成果的个人贡献未写清"],
                    [
                        f"你说{lead_hits[0]}这个项目，你具体负责决策、方案设计还是执行？",
                        "团队分工是怎样的？你个人产出是什么？",
                    ],
                    ["项目复盘文档", "代码/设计产出截图"],
                )
            )
    return items


def _reason_metric_claims(claims: List[dict]) -> List[dict]:
    items: List[dict] = []
    for c in claims:
        if c["claim_type"] != "result" and not _HIGH_PCT.search(c["text"]):
            continue
        text = c["text"]
        if not _HIGH_PCT.search(text) and not re.search(r"\d{2,}%", text):
            continue
        has_baseline = any(k in text for k in ("从", "基线", "之前", "原来", "优化前"))
        has_period = any(k in text for k in ("月", "季度", "年", "周", "天", "周期"))
        if not has_baseline or not has_period:
            items.append(
                _build_claim_item(
                    c,
                    "medium",
                    [
                        "该 claim 包含高比例提升结果",
                        "简历中未说明基线、统计周期和口径",
                        "需要确认个人贡献还是团队结果",
                    ],
                    [
                        "该数字可能来自团队整体复盘",
                        "该数字可能缺少上下文口径",
                        "候选人可能参与了其中一个模块",
                    ],
                    [
                        "转化率/指标从多少提升到多少？",
                        "统计周期是多久？",
                        "该提升是否来自 AB 实验？",
                        "你个人负责了哪一部分？",
                    ],
                    ["项目复盘截图", "AB 实验结果", "性能/业务指标截图", "直属负责人证明"],
                )
            )
    return items


def _reason_skill_claims(claims: List[dict]) -> List[dict]:
    items: List[dict] = []
    for c in claims:
        if c["claim_type"] != "skill" and c["section"] not in ("projects", "work_experience"):
            continue
        text = c["text"]
        tech_hits = [k for k in _TECH_KEYWORDS if k.lower() in text.lower()]
        if len(tech_hits) >= 3:
            has_context = any(
                k in text for k in ("场景", "瓶颈", "优化", "解决", "问题", "因为", "由于")
            )
            if not has_context:
                items.append(
                    _build_claim_item(
                        c,
                        "low",
                        [
                            f"技术关键词堆叠（{', '.join(tech_hits[:4])}）但缺少使用场景",
                            "难以判断真实技术深度",
                        ],
                        ["可能参与过相关项目但非核心开发", "可能是团队技术栈整体描述"],
                        [
                            f"你使用 {tech_hits[0]} 的具体场景是什么？解决了什么瓶颈？",
                            "你在其中具体负责哪一部分？",
                        ],
                        ["技术方案文档", "代码仓库贡献记录"],
                    )
                )
    return items


def _reason_template_claims(claims: List[dict], resume_json: dict) -> List[dict]:
    items: List[dict] = []
    template_counts: Dict[int, int] = {}
    for c in claims:
        if c["section"] != "work_experience":
            continue
        hits = detect_template_phrases(c["text"])
        if hits:
            template_counts[c["entry_index"]] = template_counts.get(c["entry_index"], 0) + len(hits)

    for entry_idx, count in template_counts.items():
        if count >= 2:
            for c in claims:
                if (
                    c["section"] == "work_experience"
                    and c["entry_index"] == entry_idx
                    and c["claim_type"] == "action"
                ):
                    items.append(
                        _build_claim_item(
                            c,
                            "low",
                            ["多段经历使用相似模板句式", "描述结构高度同质化"],
                            ["可能来自简历模板或机构统一包装", "可能是真实经历但表述模板化"],
                            ["能否详细还原其中一个项目的决策过程与您的具体动作？"],
                            ["项目详细复盘"],
                        )
                    )
                    break
    return items


def _reason_jd_gap_claims(claims: List[dict], job_json: Optional[dict]) -> List[dict]:
    items: List[dict] = []
    if not job_json:
        return items
    jd_text = " ".join(
        [
            str(job_json.get("title") or ""),
            str(job_json.get("description") or ""),
            str(job_json.get("requirements") or ""),
        ]
    ).lower()
    if not jd_text.strip():
        return items

    action_corpus = " ".join(
        c["text"].lower()
        for c in claims
        if c["section"] in ("work_experience", "projects")
        and c["claim_type"] in ("action", "result")
    )

    for c in claims:
        if c["claim_type"] != "skill" or c["section"] != "skills":
            continue
        skill = c["text"].lower()
        if skill not in jd_text:
            continue
        if skill not in action_corpus:
            items.append(
                _build_claim_item(
                    c,
                    "low",
                    ["JD 相关技能 claim 缺少经历中的具体证据", "仅有技能标签无项目佐证"],
                    ["技能可能来自学习/培训但未实际应用", "可能在其他未详述的项目中使用"],
                    [f"你在哪个项目中使用过 {c['text']}？具体做了什么？"],
                    ["项目代码/文档", "技术面试现场演示"],
                )
            )
    return items


def _dedupe_claim_items(items: List[dict]) -> List[dict]:
    seen: set = set()
    out: List[dict] = []
    for item in items:
        key = item["claim_id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _compute_overall_status(items: List[dict]) -> str:
    return "needs_clarification" if items else "clear"


def reason_about_claims(
    resume_json: dict,
    job_json: Optional[dict] = None,
) -> dict:
    """返回 claim 级审计结果。"""
    claims = extract_resume_claims(resume_json)
    events = extract_timeline_events(resume_json or {})

    claim_items: List[dict] = []
    claim_items.extend(_reason_timeline_claims(claims, events))
    claim_items.extend(_reason_seniority_claims(claims, resume_json, events))
    claim_items.extend(_reason_role_boundary_claims(claims))
    claim_items.extend(_reason_metric_claims(claims))
    claim_items.extend(_reason_skill_claims(claims))
    claim_items.extend(_reason_template_claims(claims, resume_json))
    claim_items.extend(_reason_jd_gap_claims(claims, job_json))

    claim_items = _dedupe_claim_items(claim_items)
    risk_score = compute_risk_score(claim_items, level_key="risk_level")
    overall_status = _compute_overall_status(claim_items)

    # 按风险排序
    risk_order = {"high": 0, "medium": 1, "low": 2}
    claim_items.sort(key=lambda x: risk_order.get(x["risk_level"], 3))

    # 聚合追问包
    question_themes: Dict[str, List[str]] = {}
    for item in claim_items:
        theme = {
            "result": "指标口径",
            "role": "角色边界",
            "skill": "技术深度",
            "time": "时间线",
            "title": "职级合理性",
        }.get(item["claim_type"], "综合澄清")
        question_themes.setdefault(theme, [])
        question_themes[theme].extend(item.get("verification_questions") or [])

    interview_question_pack = [
        {"theme": theme, "questions": list(dict.fromkeys(qs))[:5]}
        for theme, qs in question_themes.items()
    ]

    return {
        "overall_status": overall_status,
        "overall_status_label": STATUS_LABELS.get(overall_status, overall_status),
        "risk_score": risk_score,
        "claim_items": claim_items,
        "total_claims_extracted": len(claims),
        "flagged_claims": len(claim_items),
        "interview_question_pack": interview_question_pack,
        "disclaimer": DISCLAIMER,
        "do_not_conclude": DO_NOT_CONCLUDE,
    }


def _questions_from_audit(audit: dict, resume_json: dict) -> List[dict]:
    questions: List[dict] = []

    type_map = {
        "role": "role_boundary",
        "result": "metric_scope",
        "skill": "technical_depth",
        "action": "team_contribution",
        "time": "timeline",
        "title": "role_boundary",
    }

    why_map = {
        "role_boundary": "该 claim 缺少角色边界",
        "metric_scope": "该 claim 缺少指标口径",
        "technical_depth": "该 claim 缺少技术场景说明",
        "team_contribution": "该 claim 缺少个人贡献边界",
        "timeline": "该 claim 时间线需确认",
    }

    for item in audit.get("claim_items") or []:
        q_type = type_map.get(item["claim_type"], "team_contribution")
        vqs = item.get("verification_questions") or []
        if not vqs:
            continue
        questions.append(
            {
                "claim_id": item["claim_id"],
                "question": vqs[0],
                "question_type": q_type,
                "why_ask": why_map.get(q_type, "该 claim 需要进一步澄清"),
                "claim_text": item["claim_text"],
                "risk_level": item["risk_level"],
            }
        )

    if not questions:
        for idx, exp in enumerate(resume_json.get("work_experience") or []):
            if not isinstance(exp, dict):
                continue
            desc = (exp.get("description") or "").strip()
            if desc and not re.search(r"\d", desc):
                questions.append(
                    {
                        "claim_id": f"work_experience_{idx}_action_0",
                        "question": f"在「{exp.get('company', '该段经历')}」中，你具体负责什么？取得了哪些可量化结果？",
                        "question_type": "metric_scope",
                        "why_ask": "经历描述缺少量化与角色边界",
                        "claim_text": desc[:80],
                        "risk_level": "low",
                    }
                )

    return questions[:10]


def generate_claim_followup_pack(resume_json: dict) -> dict:
    """一次审计同时返回追问与摘要，避免重复跑规则引擎。"""
    audit = reason_about_claims(resume_json)
    return {
        "questions": _questions_from_audit(audit, resume_json or {}),
        "audit": audit,
    }


def generate_claim_followup_questions(resume_json: dict) -> List[dict]:
    """为 AI 面试官生成 claim 追问列表。"""
    return generate_claim_followup_pack(resume_json)["questions"]

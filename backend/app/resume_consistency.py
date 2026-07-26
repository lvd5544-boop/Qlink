"""
候选人侧：简历表述一致性诊断。

检测「写得真但不一致」的常见情况，并给出可操作的改稿建议（非造假判定）。
禁止无依据注入职位、责任或结果；角色不明时只提问，不生成可直接应用的 patch。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .resume_text import split_bullets

_ENG_TITLE_WORDS = ("开发", "工程师", "engineer", "后端", "前端", "架构", "java", "python", "全栈")
_PM_DESC_WORDS = (
    "产品规划",
    "PRD",
    "需求分析",
    "用户调研",
    "路线图",
    "竞品分析",
    "产品设计",
    "产品经理",
)
_TECH_IN_DESC = (
    "Python",
    "Java",
    "FastAPI",
    "React",
    "Vue",
    "Node",
    "Go",
    "Redis",
    "MySQL",
    "PostgreSQL",
    "Kafka",
    "Docker",
    "K8s",
    "Kubernetes",
    "Spring",
    "TypeScript",
    "微服务",
    "API",
    "后端",
    "前端",
    "数据库",
    "算法",
    "匹配",
    "解析",
)
# 原文已出现的角色澄清词；仅用于判断“是否已写清”，不得作为可注入模板
_ROLE_CLARIFIERS = (
    "技术负责人",
    "全栈",
    "研发主导",
    "开发兼",
    "兼负责",
    "主导研发",
    "开发工程师",
    "后端工程师",
    "前端工程师",
)


def _skill_names(resume_json: dict) -> List[str]:
    names: List[str] = []
    for s in resume_json.get("skills") or []:
        if isinstance(s, dict):
            n = (s.get("name") or "").strip()
        else:
            n = str(s).strip()
        if n:
            names.append(n.lower())
    return names


def _has_eng_intent(expected: str) -> bool:
    t = (expected or "").lower()
    return any(w in t for w in _ENG_TITLE_WORDS)


def _pm_signals_in_text(text: str) -> List[str]:
    return [w for w in _PM_DESC_WORDS if w in (text or "")]


def _tech_in_text(text: str) -> List[str]:
    blob = text or ""
    return [t for t in _TECH_IN_DESC if t.lower() in blob.lower()]


def _explicit_tech_role(position: str, desc: str = "") -> Optional[str]:
    """仅当 position/title（或描述已有澄清词）明确含技术角色时返回原文角色，否则 None。"""
    title = (position or "").strip()
    blob = f"{title}\n{desc or ''}"
    for word in _ENG_TITLE_WORDS:
        if word.lower() in title.lower():
            return title
    for c in _ROLE_CLARIFIERS:
        if c in blob:
            # 返回已出现的澄清片段，不做升级
            return c if c in title or c in (desc or "") else None
    return None


def _issue(
    *,
    issue_id: str,
    category: str,
    severity: str,
    title: str,
    detected: str,
    why: str,
    wording_fix: str,
    example_rewrite: str,
    field_path: str,
    entry_type: Optional[str] = None,
    entry_index: Optional[int] = None,
    patch: Optional[dict] = None,
    needs_followup: bool = False,
    clarification_question: Optional[str] = None,
) -> dict:
    return {
        "id": issue_id,
        "category": category,
        "severity": severity,
        "title": title,
        "detected": detected,
        "why": why,
        "wording_fix": wording_fix,
        "example_rewrite": example_rewrite,
        "field_path": field_path,
        "entry_type": entry_type,
        "entry_index": entry_index,
        "patch": patch,
        "needs_followup": needs_followup,
        "clarification_question": clarification_question,
    }


def _clarification_only_issue(
    *,
    issue_id: str,
    category: str,
    severity: str,
    title: str,
    detected: str,
    why: str,
    field_path: str,
    question: str,
    writing_frame: str,
    entry_type: Optional[str] = None,
    entry_index: Optional[int] = None,
) -> dict:
    """角色不明时：只提问 + 写作框架提示，不提供可写回 patch。"""
    return _issue(
        issue_id=issue_id,
        category=category,
        severity=severity,
        title=title,
        detected=detected,
        why=why,
        wording_fix=writing_frame,
        # 框架仅作 UI 提示，不得作为可采纳文案
        example_rewrite="",
        field_path=field_path,
        entry_type=entry_type,
        entry_index=entry_index,
        patch=None,
        needs_followup=True,
        clarification_question=question,
    )


def _check_expected_vs_experience_tone(resume_json: dict) -> List[dict]:
    issues: List[dict] = []
    expected = (resume_json.get("expected_job_title") or "").strip()
    if not expected or not _has_eng_intent(expected):
        return issues

    for idx, exp in enumerate(resume_json.get("work_experience") or []):
        if not isinstance(exp, dict):
            continue
        desc = (exp.get("description") or "").strip()
        if not desc:
            continue
        pm_hits = _pm_signals_in_text(desc)
        if not pm_hits:
            continue

        company = exp.get("company") or "该段经历"
        position = exp.get("position") or exp.get("title") or ""
        if any(c in desc for c in _ROLE_CLARIFIERS) and _explicit_tech_role(position, desc):
            continue

        role = _explicit_tech_role(position, desc)
        if role:
            # 职位本身已是技术角色：仅忠实前置已有职位名，不新增「负责人/主导」等
            suggested = (
                f"{position}，{desc}" if position and not desc.startswith(position) else desc
            )
            issues.append(
                _issue(
                    issue_id=f"expected_tone_work_{idx}",
                    category="意向与经历表述",
                    severity="medium",
                    title=f"期望职位与经历写法容易让招聘方误解（{company}）",
                    detected=f"期望「{expected}」，但经历描述出现「{'、'.join(pm_hits[:3])}」等产品向表述",
                    why="招聘方可能误以为你在投产品岗，或质疑角色边界。真实兼做产品与开发时，需要在开头写清已有技术角色。",
                    wording_fix="用原文已有的职位名称开头，再写产品规划职责；不要添加原文没有的职级或主导表述。",
                    example_rewrite=suggested[:500],
                    field_path=f"work_experience[{idx}].description",
                    entry_type="work",
                    entry_index=idx,
                    patch={
                        "action": "fill_field",
                        "section": "work_experience",
                        "index": idx,
                        "field": "description",
                        "value": suggested[:800],
                    },
                )
            )
        else:
            issues.append(
                _clarification_only_issue(
                    issue_id=f"expected_tone_work_{idx}",
                    category="意向与经历表述",
                    severity="medium",
                    title=f"期望职位与经历写法容易让招聘方误解（{company}）",
                    detected=f"期望「{expected}」，职位为「{position or '未填写'}」，描述含「{'、'.join(pm_hits[:3])}」",
                    why="原文未写明技术角色边界。在确认你的真实分工前，系统不会自动改写为技术负责人或主导研发等表述。",
                    field_path=f"work_experience[{idx}].description",
                    question=(
                        f"这段经历（{company}）里，你实际承担的技术职责边界是什么？"
                        "请用原文事实说明：是否写代码/做架构/做评审，还是以产品/协调为主？"
                    ),
                    writing_frame=(
                        "写作框架（回答后再生成可写回版本，本框架不可直接采纳）："
                        "「[真实职位]：负责[真实技术动作]；同时参与[产品相关工作]。」"
                    ),
                    entry_type="work",
                    entry_index=idx,
                )
            )

    for idx, proj in enumerate(resume_json.get("projects") or []):
        if not isinstance(proj, dict):
            continue
        desc = (proj.get("description") or "").strip()
        pm_hits = _pm_signals_in_text(desc)
        if not pm_hits:
            continue
        if any(c in desc for c in _ROLE_CLARIFIERS):
            continue
        name = proj.get("name") or "该项目"
        role = (proj.get("role") or "").strip()
        tech_role = _explicit_tech_role(role, desc)
        if tech_role and role:
            suggested = f"{role}：{desc}" if not desc.startswith(role) else desc
            issues.append(
                _issue(
                    issue_id=f"expected_tone_proj_{idx}",
                    category="意向与经历表述",
                    severity="medium",
                    title=f"项目描述偏产品叙事（{name}）",
                    detected=f"期望「{expected}」，项目描述含「{'、'.join(pm_hits[:2])}」",
                    why="自研/创业项目中开发兼产品很常见，但读者第一眼会看到「产品规划」而非个人技术贡献。",
                    wording_fix="先用原文已有的项目角色，再写产品/功能规划；不要添加未出现过的职级。",
                    example_rewrite=suggested[:500],
                    field_path=f"projects[{idx}].description",
                    entry_type="project",
                    entry_index=idx,
                    patch={
                        "action": "fill_field",
                        "section": "projects",
                        "index": idx,
                        "field": "description",
                        "value": suggested[:800],
                    },
                )
            )
        else:
            issues.append(
                _clarification_only_issue(
                    issue_id=f"expected_tone_proj_{idx}",
                    category="意向与经历表述",
                    severity="medium",
                    title=f"项目描述偏产品叙事（{name}）",
                    detected=f"期望「{expected}」，项目描述含「{'、'.join(pm_hits[:2])}」且未写明技术角色",
                    why="在确认你在该项目中的真实技术贡献前，不会自动写上「主导研发」等表述。",
                    field_path=f"projects[{idx}].description",
                    question=f"在项目「{name}」中，你具体做了哪些技术实现？请只写真实发生过的内容。",
                    writing_frame=(
                        "写作框架（不可直接采纳）：「[真实角色]：实现了[模块/技术]；并参与[产品相关工作]。」"
                    ),
                    entry_type="project",
                    entry_index=idx,
                )
            )

    return issues


def _check_skills_vs_description(resume_json: dict) -> List[dict]:
    issues: List[dict] = []
    skill_set = set(_skill_names(resume_json))

    corpus_parts: List[str] = []
    for exp in resume_json.get("work_experience") or []:
        if isinstance(exp, dict):
            corpus_parts.append(exp.get("description") or "")
    for proj in resume_json.get("projects") or []:
        if isinstance(proj, dict):
            corpus_parts.append(proj.get("description") or "")
    corpus = "\n".join(corpus_parts)

    mentioned = _tech_in_text(corpus)
    missing = [
        t
        for t in mentioned
        if t.lower() not in skill_set and not any(t.lower() in s for s in skill_set)
    ]
    missing = list(dict.fromkeys(missing))[:6]

    if len(missing) >= 2:
        skill_display = "、".join(_skill_names(resume_json)[:5]) or "（技能栏较少）"
        issues.append(
            _issue(
                issue_id="skills_gap_description",
                category="技能与描述",
                severity="medium",
                title="经历里提到的技术，技能栏未体现",
                detected=f"描述中出现 {', '.join(missing[:4])} 等，当前技能：{skill_display}",
                why="招聘方会拿技能标签核对经历。能力写在项目里但标签没写，容易被判为「描述夸大」或「技能薄弱」。",
                wording_fix="把描述中反复出现的技术补进技能栏；或把未列技能改成更笼统的表述。仅补充原文已出现的技术名。",
                example_rewrite=f"建议在技能栏补充：{'、'.join(missing[:4])}",
                field_path="skills",
                entry_type=None,
                entry_index=None,
                patch={
                    "action": "fill_field",
                    "section": "skills",
                    "field": "name",
                    "value": missing[0],
                },
            )
        )

    return issues


def _check_title_vs_bullet_role(resume_json: dict) -> List[dict]:
    issues: List[dict] = []
    for idx, exp in enumerate(resume_json.get("work_experience") or []):
        if not isinstance(exp, dict):
            continue
        title = (exp.get("position") or exp.get("title") or "").strip()
        desc = exp.get("description") or ""
        if not _explicit_tech_role(title, ""):
            continue

        for bi, bullet in enumerate(split_bullets(desc)):
            if "负责" not in bullet and "主导" not in bullet:
                continue
            if not _pm_signals_in_text(bullet):
                continue
            if any(c in bullet for c in _ROLE_CLARIFIERS):
                continue
            if _tech_in_text(bullet):
                continue

            # 只用已有职位名做忠实前置，不注入「开发负责人/主导研发」
            rewrite = f"{title}：{bullet}" if title and not bullet.startswith(title) else bullet
            issues.append(
                _issue(
                    issue_id=f"title_bullet_work_{idx}_{bi}",
                    category="角色边界",
                    severity="low",
                    title=f"职位是技术岗，但 bullet 读起来像产品（{exp.get('company') or '经历'}）",
                    detected=bullet[:120],
                    why="同一段经历里，职位名是开发，句子却像产品经理，读者会疑惑你的实际产出是写代码还是写 PRD。",
                    wording_fix="每条 bullet 用「已有职位 + 技术动作 + 业务结果」；不要添加原文没有的负责人/主导表述。",
                    example_rewrite=rewrite[:300],
                    field_path=f"work_experience[{idx}].description",
                    entry_type="work",
                    entry_index=idx,
                    patch={
                        "action": "fill_field",
                        "section": "work_experience",
                        "index": idx,
                        "field": "description",
                        "value": desc.replace(bullet, rewrite, 1)[:800],
                    },
                )
            )
            break

    return issues


def _check_summary_vs_expected(resume_json: dict) -> List[dict]:
    issues: List[dict] = []
    expected = (resume_json.get("expected_job_title") or "").strip()
    summary = (resume_json.get("summary") or "").strip()
    if not expected or not summary or not _has_eng_intent(expected):
        return issues

    pm_hits = _pm_signals_in_text(summary)
    if pm_hits and not _tech_in_text(summary):
        issues.append(
            _clarification_only_issue(
                issue_id="summary_expected_mismatch",
                category="意向与经历表述",
                severity="low",
                title="个人简介与期望职位叙事不一致",
                detected=f"期望「{expected}」，简介含「{'、'.join(pm_hits[:2])}」但缺少技术关键词",
                why="简介是招聘方第一眼看到的内容。在你确认可写的真实技术定位前，不会自动添加「全栈开发」等原文没有的能力声明。",
                field_path="summary",
                question=(
                    f"简介目前偏产品叙事，而期望职位是「{expected}」。"
                    "请补充你真实具备、且愿意写进简介的技术定位或年限（没有则不要编造）。"
                ),
                writing_frame=(
                    "写作框架（不可直接采纳）：「[真实技术定位/年限]。[原有简介中属实的部分]。」"
                ),
            )
        )

    return issues


def diagnose_resume_consistency(resume_json: Optional[dict]) -> dict:
    """
    候选人简历表述一致性诊断。
    返回 issues 列表；角色不明时仅含澄清问题，不含可写回虚构角色的 patch。
    """
    data = resume_json or {}
    issues: List[dict] = []
    issues.extend(_check_expected_vs_experience_tone(data))
    issues.extend(_check_skills_vs_description(data))
    issues.extend(_check_title_vs_bullet_role(data))
    issues.extend(_check_summary_vs_expected(data))

    # 去重：同 field_path 保留 severity 最高的一条
    severity_order = {"medium": 0, "low": 1}
    by_path: Dict[str, dict] = {}
    for item in issues:
        key = item.get("field_path") or item.get("id")
        prev = by_path.get(key)
        if not prev or severity_order.get(item["severity"], 9) < severity_order.get(
            prev["severity"], 9
        ):
            by_path[key] = item
    issues = sorted(by_path.values(), key=lambda x: severity_order.get(x["severity"], 9))

    status = "needs_attention" if issues else "clear"
    summary = (
        f"发现 {len(issues)} 处表述可能让招聘方误解，建议按提示确认角色边界或调整措辞（不是说你经历不实）。"
        if issues
        else "未发现明显的意向-经历-技能表述冲突，可继续优化量化与关键词。"
    )

    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues[:8],
        "summary": summary,
        "disclaimer": (
            "以下为「写法一致性」提醒：帮助读者快速理解你的真实角色。"
            "若经历属实，通常只需确认角色边界、调整措辞或补齐技能标签；"
            "系统不会在无证据时写入技术负责人、主导研发等新事实。"
        ),
    }

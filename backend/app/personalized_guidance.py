"""Grounded, reusable personalization for candidate-facing guidance.

The module deliberately turns observed candidate material into practice tasks.
It never converts a missing resume signal into a claim that the person lacks
the capability.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or value.get("skill") or "").strip()
    return str(value or "").strip()


def _compact(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", _text(value)).strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _project_rows(resume_json: dict | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source = resume_json or {}
    for section in ("projects", "work_experience"):
        for item in source.get(section) or []:
            if not isinstance(item, dict):
                continue
            title = _text(
                item.get("name") or item.get("title") or item.get("position") or item.get("company")
            )
            detail = _text(
                item.get("description")
                or item.get("details")
                or item.get("responsibilities")
                or item.get("achievement")
            )
            if title or detail:
                rows.append({"title": title or "一段已有经历", "detail": detail})
    return rows


def _anchor_project(resume_json: dict | None, corpus: str = "") -> dict[str, str]:
    rows = _project_rows(resume_json)
    lowered = corpus.casefold()
    for row in rows:
        if row["title"] and row["title"].casefold() in lowered:
            return row

    # When the user introduces a new experience during the interview, use that
    # actual answer as the coaching anchor instead of forcing an unrelated
    # resume project merely because its description is longer.
    answer_anchor_patterns = (
        r"(?:我在|在)([^，。；;\n]{2,36}?(?:实习|项目|课题|工作))",
        r"(?:during|at|in)\s+([^,.;\n]{2,48}?(?:internship|project|role))",
    )
    for pattern in answer_anchor_patterns:
        match = re.search(pattern, corpus, re.IGNORECASE)
        if match:
            return {"title": _compact(match.group(1), 42), "detail": _compact(corpus, 220)}

    if not rows:
        return {"title": "你本次提到的经历", "detail": _compact(corpus, 220)}
    ranked = sorted(
        rows,
        key=lambda row: (
            sum(
                1
                for token in re.findall(
                    r"[\w\u4e00-\u9fff]{3,}",
                    f"{row['title']} {row['detail']}".casefold(),
                )
                if token in lowered
            ),
            len(row["detail"]),
        ),
        reverse=True,
    )
    return ranked[0]


def _required_skills(job_json: dict | None) -> list[str]:
    values = (job_json or {}).get("required_skills") or []
    return list(dict.fromkeys(filter(None, (_text(item) for item in values))))[:6]


def _resume_skills(resume_json: dict | None) -> list[str]:
    values = (resume_json or {}).get("skills") or []
    return list(dict.fromkeys(filter(None, (_text(item) for item in values))))[:8]


def guidance_context(
    *,
    resume_json: dict | None,
    job_json: dict | None = None,
    job_title: str | None = None,
    corpus: str = "",
) -> dict[str, Any]:
    source = resume_json or {}
    basic_info = source.get("basic_info") if isinstance(source.get("basic_info"), dict) else {}
    anchor = _anchor_project(source, corpus)
    required = _required_skills(job_json)
    skills = _resume_skills(source)
    return {
        "candidate_name": _text(source.get("name") or basic_info.get("name")),
        "target_role": _text(
            job_title or (job_json or {}).get("title") or source.get("expected_job_title")
        ),
        "anchor_experience": anchor,
        "resume_skills": skills,
        "target_skills": required,
        "shared_skills": [
            skill
            for skill in skills
            if skill.casefold() in {value.casefold() for value in required}
        ],
    }


def _action(
    *,
    key: str,
    title: str,
    why: str,
    based_on: str,
    steps: Iterable[str],
    practice_prompt: str,
    success_criteria: Iterable[str],
    priority: int,
    effort: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "why": why,
        "based_on": based_on,
        "steps": list(steps),
        "practice_prompt": practice_prompt,
        "success_criteria": list(success_criteria),
        "priority": priority,
        "estimated_effort": effort,
    }


def build_interview_action_plan(
    *,
    gap_types: Iterable[str],
    resume_json: dict | None,
    job_json: dict | None,
    job_title: str | None,
    answer_corpus: str,
    recurring_gap_types: Iterable[str] = (),
) -> dict[str, Any]:
    gaps = set(gap_types)
    recurring = set(recurring_gap_types)
    context = guidance_context(
        resume_json=resume_json,
        job_json=job_json,
        job_title=job_title,
        corpus=answer_corpus,
    )
    anchor = context["anchor_experience"]
    anchor_name = anchor["title"]
    target_role = context["target_role"]
    target_skill = (
        context["shared_skills"]
        or context["target_skills"]
        or context["resume_skills"]
        or ["目标岗位能力"]
    )[0]
    basis = (
        _compact(answer_corpus, 180)
        or _compact(anchor["detail"], 180)
        or f"你已提供的「{anchor_name}」经历"
    )
    actions: list[dict[str, Any]] = []

    if "candidate_action" in gaps:
        actions.append(
            _action(
                key="ownership",
                title=f"把「{anchor_name}」中的个人贡献讲清楚",
                why="当前回答没有稳定地区分个人决策、执行动作和团队产出，招聘方难以判断你的实际责任边界。",
                based_on=basis,
                steps=[
                    "先用一句话交代团队目标和你的角色。",
                    "列出你亲自做出的一个判断、一个动作和一次协作。",
                    "把团队成果改写为“团队完成什么；其中我负责什么”。",
                ],
                practice_prompt=f"请用 60 秒重讲「{anchor_name}」，至少使用两次“我”，并明确一次由你作出的选择。",
                success_criteria=[
                    "出现清晰的个人动作",
                    "说明与团队的边界",
                    "能追问到具体过程而不矛盾",
                ],
                priority=1,
                effort="15 分钟",
            )
        )
    if "result" in gaps or "metric" in gaps:
        actions.append(
            _action(
                key="impact",
                title=f"为「{anchor_name}」补一条可信的结果证据",
                why=(
                    "这是连续面试中反复出现的薄弱模式，需要优先训练。"
                    if {"result", "metric"} & recurring
                    else "当前案例有行动，但还缺少能帮助别人判断影响的结果、范围或前后变化。"
                ),
                based_on=basis,
                steps=[
                    "先写清最终交付物或解决的问题，不强制编造百分比。",
                    "从样本量、周期、覆盖对象、准确性、效率或他人采用情况中选一个真实口径。",
                    "如果没有精确数字，注明真实范围、观察方式或定性反馈来源。",
                ],
                practice_prompt=f"请补完这句话：“在「{anchor_name}」中，我最终交付了____；通过____判断它有效；影响范围是____。”",
                success_criteria=["有明确产出", "有至少一个真实衡量口径", "口径包含范围或时间边界"],
                priority=1 if {"result", "metric"} & recurring else 2,
                effort="20 分钟",
            )
        )
    if "reflection" in gaps:
        actions.append(
            _action(
                key="reflection",
                title=f"把「{anchor_name}」从经历描述升级为能力证明",
                why=f"对{target_role or '目标岗位'}而言，说明取舍和纠偏过程比只罗列任务更能体现可迁移能力。",
                based_on=basis,
                steps=[
                    "指出当时最困难的约束或两个方案之间的取舍。",
                    "说明你依据什么作出选择，以及结果暴露了什么局限。",
                    "给出下一次会保留和改变的各一件事。",
                ],
                practice_prompt=f"围绕「{anchor_name}」回答：“如果重做一次，我会保留____，改变____，因为____。”",
                success_criteria=["出现真实约束", "解释选择依据", "给出具体的下一次行为"],
                priority=2,
                effort="15 分钟",
            )
        )
    if "completeness" in gaps:
        actions.append(
            _action(
                key="completion",
                title="建立不会漏答的 90 秒回答骨架",
                why="未完成的问题会让已有优势无法被完整观察；先稳定回答结构，再追求语言精美。",
                based_on=basis,
                steps=[
                    "用 15 秒交代情境和目标。",
                    "用 45 秒说明个人行动、方法与协作。",
                    "用 20 秒说明结果，最后 10 秒复盘。",
                ],
                practice_prompt=f"以「{anchor_name}」为例录一遍 90 秒回答，超时或缺段就立刻重录一次。",
                success_criteria=["四段结构完整", "90 秒内完成", "个人行动篇幅不少于背景"],
                priority=3,
                effort="10 分钟",
            )
        )

    if not actions:
        actions.append(
            _action(
                key="stretch",
                title=f"把「{anchor_name}」改造成更贴近 {target_skill} 的高质量案例",
                why="当前结构已经完整，下一步应提高岗位相关性和表达密度。",
                based_on=basis,
                steps=[
                    f"圈出案例中与“{target_skill}”直接相关的两个动作。",
                    "删掉不影响判断的背景信息。",
                    "准备一个针对失败、冲突或取舍的追问版本。",
                ],
                practice_prompt=f"用同一案例分别回答“你如何运用 {target_skill}”和“你会如何改进”，每题 60 秒。",
                success_criteria=["开头直接回应岗位能力", "至少一个可核对细节", "能应对一个追问"],
                priority=2,
                effort="20 分钟",
            )
        )

    actions.sort(key=lambda item: (item["priority"], item["key"]))
    return {
        "personalization_basis": {
            "anchor_experience": anchor_name,
            "target_role": target_role or None,
            "target_skill": target_skill,
            "used_resume": bool(resume_json),
            "used_job": bool(job_json),
            "used_interview_answers": bool(answer_corpus.strip()),
        },
        "north_star": (
            f"优先把「{anchor_name}」训练成一个能证明“{target_skill}”的完整案例，"
            "再迁移到其他问题；不要同时泛化修改所有经历。"
        ),
        "actions": actions[:4],
    }


def build_job_guidance(
    *,
    resume_json: dict | None,
    job_json: dict | None,
    job_title: str | None,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    context = guidance_context(
        resume_json=resume_json,
        job_json=job_json,
        job_title=job_title,
    )
    anchor = context["anchor_experience"]["title"]
    target = context["target_role"] or "目标岗位"
    actions = []
    for index, issue in enumerate(issues[:3], start=1):
        recommended = next(
            (item for item in issue.get("strategies") or [] if item.get("recommended")),
            (issue.get("strategies") or [{}])[0],
        )
        strategy = str(recommended.get("strategy") or "")
        diagnosis = str(issue.get("diagnosis") or "该项仍需补充")
        requirement = str(issue.get("target_requirement_id") or target)
        profiles = {
            "method_and_tradeoff": {
                "why": (
                    f"「{anchor}」目前能看出做过什么，但还看不出你为什么选择该方法、"
                    "受什么约束以及如何权衡；这会削弱面试官对判断力的评估。"
                ),
                "first_step": "回到该经历，写下当时比较过的两个方案、一个现实约束和最终选择理由。",
                "criteria": [
                    "补齐“方案—约束—取舍”三项",
                    "不强行添加数字，也不新增未经用户提供的事实",
                ],
            },
            "outcome_expression": {
                "why": (
                    f"「{anchor}」有行动描述，但结果对谁产生了什么变化还不清楚；"
                    "即使没有精确数字，也可以补充可核对的定性结果。"
                ),
                "first_step": "补一句真实结果：交付了什么、解决了什么问题、谁使用或受到影响。",
                "criteria": ["至少说明一个真实结果或前后变化", "无法确认的数字保持空白"],
            },
            "relevance_alignment": {
                "why": (
                    f"目标岗位关注「{requirement}」，而「{anchor}」里的相关任务没有被明确连接；"
                    "问题是相关性表达不足，不等于你没有相关能力。"
                ),
                "first_step": f"圈出「{anchor}」中最接近「{requirement}」的一项真实任务，并把它放到该经历首句。",
                "criteria": [
                    "形成一条“岗位要求→真实动作”的对应关系",
                    "只重排已有事实，不把岗位要求写成个人经历",
                ],
            },
            "career_narrative": {
                "why": (
                    f"从当前经历到「{target}」的连接尚未说明，招聘方可能把方向变化理解为随机尝试；"
                    "需要的是可验证的过渡路径，而不是泛化的求职意愿。"
                ),
                "first_step": "分别写出一项可迁移能力、一段促成转向的真实经历，以及正在补足的一项能力。",
                "criteria": [
                    "用“过去积累—转向触发—当前行动”三句讲清路径",
                    "意愿与已具备能力明确区分",
                ],
            },
            "role_clarity": {
                "why": (
                    f"当前简介没有帮助招聘方在几秒内判断你与「{target}」的连接，"
                    "需要从职业记忆中选择最有支撑的定位，而不是重复基本信息。"
                ),
                "first_step": f"用「目标角色 + 1项核心能力 + 1段最强经历证据」起草两句简介，核心证据来自「{anchor}」。",
                "criteria": [
                    "简介包含目标角色、能力和经历证据",
                    "不包含地址、电话、教育日期等基本信息",
                ],
            },
            "portfolio_or_work_sample": {
                "why": (
                    f"当前职业记忆中还没有足以让他人查看的「{requirement}」产出，"
                    "简历措辞本身无法替代作品证据。"
                ),
                "first_step": "选择一个最小可交付物：代码仓库、分析报告、演示或案例复盘，并定义一周内可完成的范围。",
                "criteria": ["产出可被打开或演示", "说明个人贡献、输入、方法与限制"],
            },
            "skill_or_experience_building": {
                "why": (
                    f"岗位要求「{requirement}」，但职业记忆中暂时没有相关经历或证据；"
                    "这属于能力建设任务，不能靠改写简历补出来。"
                ),
                "first_step": "把缺口拆成一个可练习技能和一个可验证任务，确定练习资料、截止时间与产出形式。",
                "criteria": [
                    "完成一个与岗位要求直接相关的任务",
                    "完成后新增经历 Claim 与可查看产出",
                ],
            },
            "evidence_strengthening": {
                "why": (
                    f"系统在「{anchor}」中找到了可能相关的内容，但目前只有陈述，"
                    "缺少范围、角色或来源，不能安全地直接强化措辞。"
                ),
                "first_step": "确认这段经历中的个人角色、时间范围、协作者和可引用材料；材料可以先用文字说明，不强制上传文件。",
                "criteria": [
                    "Claim 已由用户确认并补齐上下文",
                    "至少一种来源可追溯，且未扩大授权用途",
                ],
            },
        }
        profile = profiles.get(strategy)
        if profile is None:
            profile = {
                "why": (
                    f"「{diagnosis}」与「{anchor}」直接相关；本项只处理这一处，不要求重写整份简历。"
                ),
                "first_step": recommended.get("why")
                or "先核对真实经历，再决定改写或转为实践任务。",
                "criteria": (
                    ["形成可追溯的改写前后对照", "没有新增未经用户提供的事实"]
                    if issue.get("claim_ids")
                    else ["确认是否存在真实经历", "没有经历时转为学习或实践任务"]
                ),
            }
        actions.append(
            {
                "priority": index,
                "title": recommended.get("title") or diagnosis,
                "why_for_you": profile["why"],
                "start_from": anchor,
                "first_step": profile["first_step"],
                "next_action": recommended.get("next_action") or "review",
                "success_criteria": profile["criteria"],
            }
        )
    return {
        "target_role": target,
        "anchor_experience": anchor,
        "focus": f"本轮只优先解决最影响「{target}」准备度的 {max(len(actions), 1)} 项，不要求把整份简历全部重写。",
        "actions": actions,
    }

"""Rule-first interview question policy for PR12.

LLM may only render natural language; goals, bans and stop rules are decided here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "interview_policy_v1"
MAX_PROBES_PER_CLAIM = 2
MAX_CORE_QUESTIONS = 6

SESSION_MODES = frozenset({"vault_builder", "target_gap", "claim_clarification", "practice"})

DECLINE_REASONS = frozenset({"unknown", "forgot", "prefer_not_to_answer", "stop_followup"})

# Sensitive / discriminatory topics — blocked before any question is persisted.
_BANNED_PATTERNS = (
    re.compile(r"年龄|几岁|出生|生肖"),
    re.compile(r"婚|孕|生育|恋爱|男朋友|女朋友|配偶"),
    re.compile(r"民族|籍贯|户籍|宗教|信仰|党派"),
    re.compile(r"残疾|健康状况|病史|精神"),
    re.compile(r"性别取向|性取向|性生活"),
    re.compile(r"家庭出身|父母职业|房价|买房"),
)

GOAL_TEMPLATES: dict[str, str] = {
    "clarify_metric": "关于「{anchor}」，请具体说明数字是怎么统计出来的？统计口径和时间范围是什么？",
    "clarify_role": "关于「{anchor}」，你个人具体负责哪些部分？哪些是团队共同完成的？",
    "clarify_method": "关于「{anchor}」，你采用了什么方法或技术路径？为什么这样选？",
    "clarify_result": "关于「{anchor}」，最终结果如何验证？有没有客观证据或材料可补充？",
    "clarify_scope": "关于「{anchor}」，项目规模、影响范围或你的参与深度是怎样的？",
    "job_requirement": "针对岗位要求「{anchor}」，请用一段真实经历说明你如何应用过它。",
    "vault_experience": "请补充一段你希望写入职业档案的经历：背景、你的行动，以及可验证的结果。",
    "practice_behavioral": "请用一段真实或模拟经历回答：你如何处理「{anchor}」这类挑战？",
}


@dataclass(frozen=True)
class PlannedQuestion:
    question_goal: str
    question_text: str
    claim_id: str | None = None
    requirement_id: str | None = None
    competency_id: str | None = None
    core_or_probe: str = "core"


def is_sensitive_question(text: str) -> bool:
    value = text or ""
    return any(pattern.search(value) for pattern in _BANNED_PATTERNS)


def assert_question_allowed(text: str) -> None:
    if is_sensitive_question(text):
        raise ValueError("sensitive_or_discriminatory_question")


def _anchor_from_claim(claim: Any) -> str:
    text = (
        getattr(claim, "current_text", None) or getattr(claim, "original_text", None) or ""
    ).strip()
    return text[:80] or "该主张"


def _goal_for_claim_type(claim_type: str | None) -> str:
    mapping = {
        "result": "clarify_result",
        "metric": "clarify_metric",
        "role": "clarify_role",
        "skill": "clarify_method",
        "action": "clarify_method",
        "time": "clarify_scope",
    }
    return mapping.get((claim_type or "").lower(), "clarify_scope")


def plan_core_questions(
    *,
    mode: str,
    claim: Any | None = None,
    resume_json: dict | None = None,
    job: Any | None = None,
) -> list[PlannedQuestion]:
    if mode not in SESSION_MODES:
        raise ValueError("invalid_mode")

    if mode == "claim_clarification":
        if claim is None:
            raise ValueError("claim_required")
        goal = _goal_for_claim_type(getattr(claim, "claim_type", None))
        text = GOAL_TEMPLATES[goal].format(anchor=_anchor_from_claim(claim))
        assert_question_allowed(text)
        return [
            PlannedQuestion(
                question_goal=goal,
                question_text=text,
                claim_id=str(claim.id),
                core_or_probe="core",
            )
        ]

    if mode == "target_gap":
        if job is None:
            raise ValueError("job_required")
        required = (getattr(job, "parsed_json", None) or {}).get("required_skills") or []
        planned: list[PlannedQuestion] = []
        # Deterministic order for same-job stability.
        normalized = []
        for item in required:
            name = item.get("name") if isinstance(item, dict) else str(item)
            name = (name or "").strip()
            if name:
                normalized.append(name)
        normalized = sorted(set(normalized), key=lambda value: value.lower())
        seed = hashlib.sha256(
            f"{getattr(job, 'id', '')}:{','.join(normalized)}".encode()
        ).hexdigest()
        # Stable rotation based on seed, but same inputs → same order.
        rotated = sorted(
            normalized,
            key=lambda name: hashlib.sha256(f"{seed}:{name.lower()}".encode()).hexdigest(),
        )
        for name in rotated[:MAX_CORE_QUESTIONS]:
            text = GOAL_TEMPLATES["job_requirement"].format(anchor=name)
            assert_question_allowed(text)
            planned.append(
                PlannedQuestion(
                    question_goal="job_requirement",
                    question_text=text,
                    requirement_id=f"requirement:{name.lower()}",
                    competency_id=name.lower(),
                    core_or_probe="core",
                )
            )
        if not planned:
            raise ValueError("job_requirements_empty")
        return planned

    if mode == "practice":
        text = GOAL_TEMPLATES["practice_behavioral"].format(anchor="跨团队协作冲突")
        assert_question_allowed(text)
        return [
            PlannedQuestion(
                question_goal="practice_behavioral",
                question_text=text,
                core_or_probe="core",
            )
        ]

    # vault_builder default
    anchors: list[str] = []
    for section in ("projects", "work_experience"):
        for item in (resume_json or {}).get(section) or []:
            if not isinstance(item, dict):
                continue
            anchor = (
                item.get("name") or item.get("title") or item.get("position") or item.get("company")
            )
            if anchor:
                anchors.append(str(anchor).strip())
    focus = anchors[0] if anchors else "你最希望招聘方了解的一段经历"
    planned = [
        PlannedQuestion(
            question_goal="vault_experience",
            question_text=f"请先完整介绍「{focus}」：当时的背景、目标和你承担的角色是什么？",
        ),
        PlannedQuestion(
            question_goal="clarify_role",
            question_text=f"在「{focus}」中，哪些工作是你独立负责的，哪些是团队共同完成的？",
        ),
        PlannedQuestion(
            question_goal="clarify_method",
            question_text=f"你在「{focus}」中采用了什么方法或技术路径？为什么这样选择？",
        ),
        PlannedQuestion(
            question_goal="clarify_result",
            question_text=f"「{focus}」最终产生了什么结果？请说明衡量口径、基线和时间范围；没有数字也可以如实说明。",
        ),
        PlannedQuestion(
            question_goal="clarify_scope",
            question_text=f"有哪些作品、报告、链接或他人反馈可以支撑「{focus}」？没有材料不会影响继续完成。",
        ),
    ]
    for item in planned:
        assert_question_allowed(item.question_text)
    return planned[:MAX_CORE_QUESTIONS]


def plan_probe_question(
    *,
    claim: Any | None,
    prior_probe_count: int,
    last_goal: str | None,
) -> PlannedQuestion | None:
    if prior_probe_count >= MAX_PROBES_PER_CLAIM:
        return None
    if claim is None:
        return None
    # Rotate among clarify goals without repeating the last one.
    goals = ["clarify_metric", "clarify_role", "clarify_method", "clarify_result"]
    next_goal = next((g for g in goals if g != last_goal), goals[0])
    text = GOAL_TEMPLATES[next_goal].format(anchor=_anchor_from_claim(claim))
    assert_question_allowed(text)
    return PlannedQuestion(
        question_goal=next_goal,
        question_text=text,
        claim_id=str(claim.id),
        core_or_probe="probe",
    )


def extract_observations_from_answer(
    answer_text: str,
    *,
    claim_id: str | None = None,
    question_goal: str | None = None,
) -> list[dict[str, Any]]:
    """Rule-based span extractor; offsets always point into answer_text."""
    text = answer_text or ""
    if not text.strip():
        return []

    observations: list[dict[str, Any]] = []
    seen_types: set[str] = set()

    def add(kind: str, span: str, start: int) -> None:
        value = span.strip()
        adjusted = start + len(span) - len(span.lstrip())
        if not value or kind in seen_types or text[adjusted : adjusted + len(value)] != value:
            return
        observations.append(
            {
                "observation_type": kind,
                "text": value,
                "source_start": adjusted,
                "source_end": adjusted + len(value),
                "claim_id": claim_id,
            }
        )
        seen_types.add(kind)

    sentence_matches = list(re.finditer(r"[^。！？\n]+", text))
    for match in sentence_matches:
        sentence = match.group(0)
        lowered = sentence.casefold()
        if re.search(r"\d+(?:\.\d+)?%?", sentence):
            add("metric", sentence, match.start())
        if re.search(
            r"结果|最终|交付|完成|实现|提升|降低|解决|产出|上线|获奖|result|delivered|improved|reduced|achieved|completed",
            lowered,
        ):
            add("result", sentence, match.start())
        if re.search(
            r"使用|采用|通过|模型|方法|框架|算法|分析|设计|实现|using|used|method|approach|designed|implemented|analy",
            lowered,
        ):
            add("method", sentence, match.start())
        if re.search(
            r"学到|复盘|取舍|权衡|反思|下次|如果重来|改进|learned|trade.?off|next time|would change|retrospect",
            lowered,
        ):
            add("reflection", sentence, match.start())
        if re.search(r"(^|[，,。\s])(我|本人|i)\s*", lowered) and re.search(
            r"负责|完成|推动|选择|协调|开发|设计|实现|分析|搭建|带领|主导|决定|wrote|built|led|owned|developed|designed|implemented|analyzed|chose",
            lowered,
        ):
            add("candidate_action", sentence, match.start())
        if len(observations) >= 6:
            break

    # The question goal is useful evidence about what a sufficiently specific
    # answer was attempting to address, but never creates a missing observation.
    if question_goal == "clarify_role" and "candidate_action" not in seen_types:
        for match in sentence_matches:
            if re.search(r"我|本人|\bi\b", match.group(0), re.IGNORECASE):
                add("candidate_action", match.group(0), match.start())
                break
    if not observations and sentence_matches:
        add("candidate_action", sentence_matches[0].group(0), sentence_matches[0].start())
    return observations


def validate_observation_offsets(answer_text: str, start: int, end: int, obs_text: str) -> bool:
    if start < 0 or end < start or end > len(answer_text):
        return False
    return answer_text[start:end] == obs_text

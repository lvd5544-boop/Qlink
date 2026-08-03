"""PR9 deterministic, provenance-aware match improvement simulation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any

from .company_registry import normalize_skill_name
from .job_profile import CROSSWALK_VERSION, build_target_role_profile
from .matching_hybrid import hybrid_score_v2

ISSUE_TYPES = frozenset(
    {
        "presentation_gap",
        "relevance_gap",
        "evidence_gap",
        "differentiation_gap",
        "capability_gap",
        "credibility_risk",
        "career_narrative_gap",
        "hard_constraint",
    }
)
STRATEGIES = frozenset(
    {
        "relevance_alignment",
        "role_clarity",
        "method_and_tradeoff",
        "scope_and_complexity",
        "outcome_expression",
        "quantification",
        "evidence_strengthening",
        "career_narrative",
        "portfolio_or_work_sample",
        "skill_or_experience_building",
        "constraint_acknowledgement",
    }
)
RULE_VERSION = "pr9-deterministic-v1"
TAXONOMY_VERSION = CROSSWALK_VERSION


def _skills(values: list[Any]) -> set[str]:
    return {
        normalize_skill_name(item.get("name", "") if isinstance(item, dict) else str(item))
        for item in values or []
    } - {""}


def _requirements(profile: dict) -> list[str]:
    return [
        str(requirement["canonical_skill"])
        for requirement in profile["requirements"]
        if requirement["kind"] == "skill"
    ]


def _claim_ids_for_text(claims: list[dict], terms: list[str]) -> list[str]:
    hits = []
    for claim in claims:
        text = str(claim.get("current_text") or "").lower()
        if any(term.lower() in text for term in terms):
            hits.append(str(claim["id"]))
    return hits


def _has_traced_number(claims: list[dict]) -> bool:
    """A number is usable only when it is in a Passport claim with user evidence."""
    return any(
        claim.get("evidence_state") == "supported_by_user_evidence"
        and re.search(r"\d", str(claim.get("current_text") or ""))
        for claim in claims
    )


def _action_type(strategy: str) -> str:
    if strategy in {
        "evidence_strengthening",
        "method_and_tradeoff",
        "outcome_expression",
        "quantification",
    }:
        return "evidence_completion"
    if strategy in {
        "relevance_alignment",
        "role_clarity",
        "scope_and_complexity",
        "career_narrative",
    }:
        return "resume_reframing"
    if strategy == "skill_or_experience_building":
        return "experience_building"
    if strategy == "constraint_acknowledgement":
        return "hard_constraint"
    return "skill_learning"


def _fingerprint(value: object) -> str:
    """Persistable input reference for a deterministic simulation replay."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _append_claim_text(hypothetical: dict, claims: list[dict], *, numeric_only: bool) -> None:
    """Model evidence already supplied by the candidate; never invent a metric."""
    texts = [
        str(claim.get("current_text") or "").strip()
        for claim in claims
        if claim.get("evidence_state") == "supported_by_user_evidence"
        and (not numeric_only or re.search(r"\d", str(claim.get("current_text") or "")))
    ]
    if not texts:
        return
    experiences = list(hypothetical.get("work_experience") or [])
    experiences.append(
        {
            "company": "候选人已提供的佐证",
            "position": "证据补充（仅模拟）",
            "description": "；".join(texts),
        }
    )
    hypothetical["work_experience"] = experiences


def _rescore(resume: dict, job: dict, job_title: str) -> float:
    has_planned = any(
        isinstance(item, dict) and str(item.get("level") or "").lower() == "planned"
        for item in (resume.get("skills") or [])
    )
    score, _, _, _ = hybrid_score_v2(
        resume, job, job_title, include_planned=has_planned
    )
    return score


def _apply_selected_counterfactual(
    resume: dict,
    job: dict,
    job_title: str,
    claims: list[dict],
    selected: set[str],
    allowed: dict[str, dict],
) -> tuple[dict, dict, dict]:
    """Build cumulative expression/evidence/capability scenarios for the same scorer."""
    expression = deepcopy(resume)
    strategies = {allowed[strategy_id]["strategy"] for strategy_id in selected}

    if strategies & {"relevance_alignment", "role_clarity", "career_narrative"}:
        expression["expected_job_title"] = job_title or str(job.get("title") or "")

    evidence = deepcopy(expression)
    evidence_strategies = {
        "evidence_strengthening",
        "method_and_tradeoff",
        "outcome_expression",
        "quantification",
        "scope_and_complexity",
        "portfolio_or_work_sample",
    }
    if strategies & evidence_strategies:
        _append_claim_text(
            evidence,
            claims,
            numeric_only=strategies == {"quantification"},
        )

    capability = deepcopy(evidence)
    future_skills = sorted(
        {skill for strategy_id in selected for skill in allowed[strategy_id]["planned_skills"]}
    )
    if future_skills:
        present = _skills(capability.get("skills") or [])
        capability["skills"] = list(capability.get("skills") or []) + [
            {"name": skill, "level": "planned"} for skill in future_skills if skill not in present
        ]
    return expression, evidence, capability


def _option(
    issue_id: str,
    strategy: str,
    title: str,
    why: str,
    *,
    requires_evidence: bool,
    can_apply_now: bool,
    next_action: str,
    dimensions: list[str],
    horizon: str,
    cost: str,
    planned_skills: list[str] | None = None,
) -> dict:
    return {
        "strategy_id": f"{issue_id}:{strategy}",
        "strategy": strategy,
        "action_type": _action_type(strategy),
        "title": title,
        "why": why,
        "requires_evidence": requires_evidence,
        "can_apply_now": can_apply_now,
        "next_action": next_action,
        "affected_dimensions": dimensions,
        "time_horizon": horizon,
        "user_cost": cost,
        "estimated_delta": 0.0,
        "planned_skills": planned_skills or [],
    }


def build_simulation(
    resume: dict,
    job: dict,
    job_title: str,
    claims: list[dict],
    selected_ids: list[str] | None = None,
) -> dict:
    """Build issues/options then re-score one complete, server-owned counterfactual."""
    current, breakdown, _, _ = hybrid_score_v2(resume, job, job_title)
    profile = build_target_role_profile(job, job_title)
    requirements = _requirements(profile)
    requirement_refs = {
        str(requirement.get("canonical_skill")): str(requirement["requirement_id"])
        for requirement in profile["requirements"]
        if requirement["kind"] == "skill"
    }
    present = _skills(resume.get("skills") or [])
    missing = [skill for skill in requirements if skill not in present]
    issues: list[dict] = []

    summary = str(resume.get("summary") or "").strip()
    if len(summary) < 40:
        issue_id = "presentation:summary"
        options = [
            _option(
                issue_id,
                "role_clarity",
                "明确目标岗位与职责边界",
                "当前简介不足以让招聘方快速判断岗位相关性。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="preview_rewrite",
                dimensions=["relevance", "expression"],
                horizon="immediate",
                cost="low",
            ),
            _option(
                issue_id,
                "method_and_tradeoff",
                "补充方法与取舍",
                "用已有经历说明如何做出关键选择，不添加新事实。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["expression", "credibility"],
                horizon="immediate",
                cost="low",
            ),
        ]
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "presentation_gap",
                "target_requirement_id": "resume.summary",
                "claim_ids": _claim_ids_for_text(claims, ["负责", "项目"]),
                "diagnosis": "简介缺少可核对的职责、方法或目标岗位信息。",
                "source_refs": ["resume.summary"],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    if not (resume.get("projects") or []):
        issue_id = "differentiation:work_sample"
        options = [
            _option(
                issue_id,
                "portfolio_or_work_sample",
                "准备可核对的作品或案例",
                "用真实产出展示与岗位相关的复杂度和范围。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["differentiation", "credibility"],
                horizon="medium_term",
                cost="medium",
            ),
            _option(
                issue_id,
                "scope_and_complexity",
                "补充已有项目的范围与复杂度",
                "优先补充已有经历的系统边界、协作方式和约束。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_claim_passport",
                dimensions=["differentiation", "expression"],
                horizon="immediate",
                cost="low",
            ),
        ]
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "differentiation_gap",
                "target_requirement_id": "portfolio_or_work_sample",
                "claim_ids": [],
                "diagnosis": "当前简历未提供独立作品或可展示案例。",
                "source_refs": ["resume.projects"],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    if missing:
        issue_id = "capability:missing_skills"
        claim_ids = _claim_ids_for_text(claims, missing)
        issue_type = "evidence_gap" if claim_ids else "capability_gap"
        options = [
            _option(
                issue_id,
                "skill_or_experience_building",
                "创建真实学习或项目计划",
                "岗位要求当前未被简历技能证据覆盖。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="create_growth_plan",
                dimensions=["skills"],
                horizon="medium_term",
                cost="medium",
                planned_skills=missing,
            ),
            _option(
                issue_id,
                "portfolio_or_work_sample",
                "准备作品或案例",
                "用可展示的真实产出补充技能证据。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["skills", "credibility"],
                horizon="medium_term",
                cost="medium",
            ),
        ]
        if claim_ids:
            options.insert(
                0,
                _option(
                    issue_id,
                    "evidence_strengthening",
                    "关联现有履历证据",
                    "已有主张可能包含相关经验，先补充可核对的背景。",
                    requires_evidence=True,
                    can_apply_now=False,
                    next_action="open_claim_passport",
                    dimensions=["skills", "credibility"],
                    horizon="immediate",
                    cost="low",
                ),
            )
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": issue_type,
                "target_requirement_id": "skills",
                "claim_ids": claim_ids,
                "diagnosis": "当前简历未观察到所需技能的充分证据。",
                "source_refs": [*(requirement_refs[skill] for skill in missing), *claim_ids],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    impact = (breakdown.get("impact") or {}).get("ratio", 0)
    if impact < 0.55:
        issue_id = "evidence:impact"
        options = [
            _option(
                issue_id,
                "method_and_tradeoff",
                "补充方法与权衡",
                "无需编造数字，也可说明问题、方案选择和限制。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["impact", "credibility"],
                horizon="immediate",
                cost="low",
            ),
            _option(
                issue_id,
                "outcome_expression",
                "表达已有定性结果",
                "仅使用可说明的真实结果，不强制量化。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_claim_passport",
                dimensions=["impact"],
                horizon="immediate",
                cost="low",
            ),
        ]
        if _has_traced_number(claims):
            options.append(
                _option(
                    issue_id,
                    "quantification",
                    "核对后表达已有数字",
                    "仅使用 Passport 中已有且带用户证据的数字，不生成占位数字。",
                    requires_evidence=True,
                    can_apply_now=True,
                    next_action="preview_rewrite",
                    dimensions=["impact", "credibility"],
                    horizon="immediate",
                    cost="low",
                )
            )
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "evidence_gap",
                "target_requirement_id": "impact",
                "claim_ids": _claim_ids_for_text(claims, ["负责", "开发", "项目"]),
                "diagnosis": "当前影响力证据不足；这不代表没有能力。",
                "source_refs": ["matching.impact"],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    role_ratio = (breakdown.get("role_match") or {}).get("ratio", 1)
    if role_ratio < 0.55:
        issue_id = "relevance:role_direction"
        options = [
            _option(
                issue_id,
                "relevance_alignment",
                "突出已有相关任务",
                "仅重组已存在的相关职责，不添加新能力。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="preview_rewrite",
                dimensions=["relevance"],
                horizon="immediate",
                cost="low",
            ),
            _option(
                issue_id,
                "career_narrative",
                "说明转向路径",
                "把真实的学习、项目和转岗动机串成可核对的职业叙事。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["relevance", "credibility"],
                horizon="immediate",
                cost="low",
            ),
        ]
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "relevance_gap",
                "target_requirement_id": "role_direction",
                "claim_ids": [],
                "diagnosis": "当前经历与目标岗位方向的直接关联较弱。",
                "source_refs": [profile["source"]["jd_snapshot_sha256"], "matching.role_match"],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )
        narrative_id = "career:transition"
        narrative_options = [
            _option(
                narrative_id,
                "career_narrative",
                "说明真实的转向路径",
                "串联现有学习、项目与岗位目标，避免把意愿写成已有能力。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="open_evidence_followup",
                dimensions=["relevance", "credibility"],
                horizon="immediate",
                cost="low",
            ),
            _option(
                narrative_id,
                "portfolio_or_work_sample",
                "用作品证明转向准备",
                "以真实项目或公开作品补充转向所需证据。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="create_growth_plan",
                dimensions=["relevance", "capability"],
                horizon="medium_term",
                cost="medium",
            ),
        ]
        issues.append(
            {
                "issue_id": narrative_id,
                "issue_type": "career_narrative_gap",
                "target_requirement_id": "career_transition",
                "claim_ids": [],
                "diagnosis": "岗位方向变化缺少可验证的职业叙事。",
                "source_refs": [
                    "resume.expected_job_title",
                    profile["source"]["jd_snapshot_sha256"],
                ],
                "strategy_options": narrative_options,
                "recommended_strategy_id": narrative_options[0]["strategy_id"],
            }
        )

    conflict_ids = [
        str(claim["id"]) for claim in claims if claim.get("evidence_state") == "conflict_detected"
    ]
    if conflict_ids:
        issue_id = "credibility:conflict"
        options = [
            _option(
                issue_id,
                "evidence_strengthening",
                "回应待处理冲突",
                "先补充来源和时间范围；冲突不能通过润色消除。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="answer_question",
                dimensions=["credibility"],
                horizon="immediate",
                cost="low",
            ),
            _option(
                issue_id,
                "constraint_acknowledgement",
                "保留待澄清状态",
                "在证据不足时不对事实作结论。",
                requires_evidence=False,
                can_apply_now=False,
                next_action="open_claim_passport",
                dimensions=["credibility"],
                horizon="immediate",
                cost="low",
            ),
        ]
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "credibility_risk",
                "target_requirement_id": "claim_conflict",
                "claim_ids": conflict_ids,
                "diagnosis": "存在待处理的信息冲突，需要澄清而非改写。",
                "source_refs": conflict_ids,
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    required_years = float(job.get("experience_years") or 0)
    actual_years = sum(
        float(item.get("duration_years") or 0)
        for item in resume.get("work_experience") or []
        if isinstance(item, dict)
    )
    if required_years and actual_years < required_years:
        issue_id = "constraint:experience"
        options = [
            _option(
                issue_id,
                "constraint_acknowledgement",
                "查看替代岗位或长期路径",
                "年限短期不能由文字修改解决。",
                requires_evidence=False,
                can_apply_now=False,
                next_action="view_alternative_roles",
                dimensions=["experience"],
                horizon="long_term",
                cost="medium",
            ),
            _option(
                issue_id,
                "skill_or_experience_building",
                "规划可验证项目经验",
                "通过真实项目积累相关经历，不写成已具备。",
                requires_evidence=True,
                can_apply_now=False,
                next_action="create_growth_plan",
                dimensions=["experience"],
                horizon="long_term",
                cost="high",
            ),
        ]
        issues.append(
            {
                "issue_id": issue_id,
                "issue_type": "hard_constraint",
                "target_requirement_id": "experience_years",
                "claim_ids": [],
                "diagnosis": f"岗位要求约 {required_years:g} 年经验，当前记录约 {actual_years:g} 年。",
                "source_refs": ["job.experience_years"],
                "strategy_options": options,
                "recommended_strategy_id": options[0]["strategy_id"],
            }
        )

    selected = set(
        [issue["recommended_strategy_id"] for issue in issues]
        if selected_ids is None
        else selected_ids
    )
    allowed = {opt["strategy_id"]: opt for issue in issues for opt in issue["strategy_options"]}
    unknown = selected - set(allowed)
    if unknown:
        raise ValueError("包含未知或不可用的策略")
    expression_input, evidence_input, hypothetical = _apply_selected_counterfactual(
        resume, job, job_title, claims, selected, allowed
    )
    expression_score = _rescore(expression_input, job, job_title)
    evidence_score = _rescore(evidence_input, job, job_title)
    potential = _rescore(hypothetical, job, job_title)
    selected_options = [allowed[sid] for sid in sorted(selected)]
    evidence_strategies = {
        "evidence_strengthening",
        "method_and_tradeoff",
        "outcome_expression",
        "quantification",
        "scope_and_complexity",
        "portfolio_or_work_sample",
    }
    has_supported_evidence = any(
        claim.get("evidence_state") == "supported_by_user_evidence" for claim in claims
    )
    selection_effects = []
    for strategy_id in sorted(selected):
        reduced = selected - {strategy_id}
        _, _, reduced_hypothetical = _apply_selected_counterfactual(
            resume, job, job_title, claims, reduced, allowed
        )
        marginal_delta = round(potential - _rescore(reduced_hypothetical, job, job_title), 2)
        option = allowed[strategy_id]
        if abs(marginal_delta) >= 0.005:
            effect_status = "changes_score_if_removed"
        elif option["strategy"] in evidence_strategies and not has_supported_evidence:
            effect_status = "needs_supported_evidence"
        else:
            effect_status = "overlaps_or_no_scoring_effect"
        selection_effects.append(
            {
                "strategy_id": strategy_id,
                "marginal_delta": marginal_delta,
                "status": effect_status,
            }
        )
    # A total counterfactual is intentionally *not* apportioned across options:
    # dimensions overlap, so addition would invent precision and double-count.
    # The only authoritative delta is the one re-scored full counterfactual below.
    jd_completeness = min(1.0, (len(requirements) + (1 if required_years else 0)) / 4)
    coverage = min(1.0, len(issues) / max(1, len(requirements) + 1))
    confidence = round(0.35 + 0.35 * jd_completeness + 0.2 * coverage + 0.1, 2)
    return {
        "current_score": current,
        "potential_score": potential,
        "potential_delta": round(potential - current, 2),
        "expression_delta": round(expression_score - current, 2),
        "evidence_delta": round(evidence_score - expression_score, 2),
        "capability_delta": round(potential - evidence_score, 2),
        "confidence": min(1.0, confidence),
        "confidence_basis": {
            "jd_parse_completeness": jd_completeness,
            "rule_coverage": coverage,
            "simulation_stability": 1.0,
        },
        "assumptions": [
            "仅为当前规则版本内的相对模拟；组合策略作为完整输入重算，不相加。",
            "表达和证据路径只复用候选人已提供的 Passport 内容；无可计分证据时 delta 可以为 0。",
            "未提供的能力不会写回当前简历。",
        ],
        "issues": issues,
        "selected_strategy_ids": sorted(selected),
        "selected_actions": selected_options,
        "selection_effects": selection_effects,
        "rule_version": RULE_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "target_role_profile": profile,
        "source_versions": {
            "resume_snapshot_sha256": _fingerprint(resume),
            "job_snapshot_sha256": _fingerprint(job),
            "target_role_profile_sha256": _fingerprint(profile),
            "claim_snapshot_sha256": _fingerprint(claims),
            "scoring_version": "hybrid_v2",
            "prompt_version": None,
            "model_version": None,
        },
    }

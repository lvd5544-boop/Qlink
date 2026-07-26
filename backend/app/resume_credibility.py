"""
招聘方侧：履历逻辑一致性 & 可信度筛查引擎。

产品原则：输出「需澄清 / 建议复核」，不直接判定「造假」。
架构：结构化抽取 → 时间线 → 规则引擎 → 同质化检测 → 语义软判断（可选 LLM）
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional

from .audit_scoring import STATUS_LABELS, compute_risk_score
from .faithful_expansion import (
    detect_packaging_in_text,
    detect_template_phrases,
)
from .resume_timeline import (
    estimate_work_years,
    extract_timeline_events,
    overlap_months,
)
from .provider_costs import extract_provider_usage

logger = logging.getLogger(__name__)

# 业绩模板化：多个极高增长表述
_METRIC_HYPE = re.compile(r"(提升|增长|降低|减少|优化).{0,6}(\d{2,3}%|百分之[八九九十百])")


def _run_timeline_rules(events: List[dict]) -> List[dict]:
    findings: List[dict] = []

    works = [e for e in events if e["type"] == "work" and e.get("start") and e.get("end")]
    edus = [e for e in events if e["type"] == "education" and e.get("start") and e.get("end")]
    projects = [e for e in events if e["type"] == "project" and e.get("start") and e.get("end")]

    # 多段全职重叠
    for i, w1 in enumerate(works):
        for w2 in works[i + 1 :]:
            if w1.get("employment_type") != "全职" or w2.get("employment_type") != "全职":
                continue
            ov = overlap_months(w1["start"], w1["end"], w2["start"], w2["end"])
            if ov > 1:
                findings.append(
                    {
                        "category": "时间线冲突",
                        "severity": "high" if ov > 3 else "medium",
                        "claim": f"{w1['label']} 与 {w2['label']}",
                        "issue": f"两段全职经历重叠约 {ov} 个月",
                        "recommendation": "建议要求候选人说明是否存在兼职/远程/简历日期笔误，或提供在职证明。",
                        "clarification_questions": [
                            "这两段经历是否存在时间重叠？若有，请说明工作形态（全职/兼职/远程）。",
                        ],
                    }
                )

    # 全日制学历与全职工作重叠
    for edu in edus:
        if "非全日制" in str(edu.get("study_type", "")) or "在职" in str(edu.get("study_type", "")):
            continue
        for w in works:
            if w.get("employment_type") != "全职":
                continue
            ov = overlap_months(edu["start"], edu["end"], w["start"], w["end"])
            if ov > 3:
                findings.append(
                    {
                        "category": "时间线冲突",
                        "severity": "high",
                        "claim": f"{edu['label']}（{edu.get('study_type')}）与 {w['label']}",
                        "issue": f"标注为全日制/未说明类型的学历与全职工作重叠约 {ov} 个月",
                        "recommendation": "建议核实是否为非全日制、远程实习或日期填写错误。",
                        "clarification_questions": [
                            "硕士/本科是否为全日制？同期全职工作如何安排？",
                        ],
                    }
                )

    # 项目不在任职期间
    for proj in projects:
        in_range = False
        for w in works:
            if not (proj.get("start") and w.get("start") and w.get("end")):
                continue
            if (
                overlap_months(proj["start"], proj["end"] or proj["start"], w["start"], w["end"])
                > 0
            ):
                in_range = True
                break
        if works and proj.get("start") and not in_range:
            findings.append(
                {
                    "category": "时间线冲突",
                    "severity": "medium",
                    "claim": proj["label"],
                    "issue": "项目时间不在任何一段工作经历区间内",
                    "recommendation": "建议追问项目是在职期间、实习还是独立/外包项目。",
                    "clarification_questions": [
                        f"「{proj['label']}」是在哪家公司任职期间完成的？",
                    ],
                }
            )

    return findings


def _run_seniority_rules(resume_json: dict, events: List[dict]) -> List[dict]:
    findings: List[dict] = []
    years = estimate_work_years(events)

    senior_titles = ("总监", "VP", "副总裁", "负责人", "CTO", "CEO", "总经理", "架构师")
    for exp in resume_json.get("work_experience") or []:
        if not isinstance(exp, dict):
            continue
        title = (exp.get("position") or exp.get("title") or "").strip()
        desc = exp.get("description") or ""
        if not title:
            continue

        if years < 2 and any(t in title for t in senior_titles):
            findings.append(
                {
                    "category": "职级合理性",
                    "severity": "medium",
                    "claim": f"{exp.get('company')} · {title}",
                    "issue": f"工作年限约 {years} 年，但职位含高级头衔",
                    "recommendation": "建议面试中核实汇报线、团队规模与决策范围。",
                    "clarification_questions": [
                        "该职位的汇报对象是谁？您直接管理多少人？",
                    ],
                }
            )

        team_match = re.search(r"(\d+)\s*人", desc + title)
        if team_match and years < 3:
            n = int(team_match.group(1))
            if n >= 20:
                findings.append(
                    {
                        "category": "职级合理性",
                        "severity": "medium",
                        "claim": f"声称管理 {n} 人团队",
                        "issue": f"工作年限约 {years} 年，管理规模偏大",
                        "recommendation": "建议追问组织结构、管理幅度与具体职责。",
                        "clarification_questions": [
                            f"管理 {n} 人是直接汇报还是含虚线/矩阵？",
                        ],
                    }
                )

    return findings


def _run_packaging_and_template_rules(resume_json: dict) -> List[dict]:
    """机构包装 / 同质化模板检测。"""
    findings: List[dict] = []
    all_text_parts: List[str] = []

    for exp in resume_json.get("work_experience") or []:
        if isinstance(exp, dict):
            all_text_parts.append(exp.get("description") or "")
    for proj in resume_json.get("projects") or []:
        if isinstance(proj, dict):
            all_text_parts.append(proj.get("description") or "")
    all_text_parts.append(resume_json.get("summary") or "")
    corpus = "\n".join(all_text_parts)

    template_hits = detect_template_phrases(corpus)
    packaging_hits = detect_packaging_in_text(corpus)
    hype_hits = _METRIC_HYPE.findall(corpus)

    if len(template_hits) >= 3:
        findings.append(
            {
                "category": "机构包装/同质化",
                "severity": "medium",
                "claim": "简历多处出现常见模板句式",
                "issue": f"命中 {len(template_hits)} 处机构/培训班常见表述：{'、'.join(template_hits[:4])}{'…' if len(template_hits) > 4 else ''}",
                "recommendation": "建议面试深挖具体项目细节，验证是否为模板化包装而非真实经历。",
                "clarification_questions": [
                    "请具体描述其中一个项目的背景、您的角色、关键决策与可验证结果。",
                    "这些表述中哪一部分是您个人独立完成的？",
                ],
                "template_phrases": template_hits,
            }
        )

    if len(packaging_hits) >= 4:
        findings.append(
            {
                "category": "语义模糊/包装词",
                "severity": "low",
                "claim": "职责描述中包装词密度较高",
                "issue": f"出现 {len(packaging_hits)} 处包装词：{'、'.join(packaging_hits[:5])}",
                "recommendation": "建议追问具体职责边界，区分「主导/参与/协助」。",
                "clarification_questions": [
                    "您提到「主导/负责」的具体范围是什么？是否有团队成员分工？",
                ],
            }
        )

    if len(hype_hits) >= 3:
        findings.append(
            {
                "category": "业绩表述",
                "severity": "medium",
                "claim": "多处极高比例业绩表述",
                "issue": f"发现 {len(hype_hits)} 处高增长/高降低表述，缺少基数与时间范围",
                "recommendation": "建议追问数据口径、统计周期与基线数值。",
                "clarification_questions": [
                    "这些提升指标的基线是多少？统计周期是多长？",
                    "该成果是您个人贡献还是团队整体结果？",
                ],
            }
        )

    #  bullet 结构同质化：多段都以「通过…使…提升…%」开头
    bullet_pattern = re.compile(r"通过.{2,20}(提升|降低|优化).{0,10}\d+")
    similar_bullets = bullet_pattern.findall(corpus)
    if len(similar_bullets) >= 2:
        findings.append(
            {
                "category": "机构包装/同质化",
                "severity": "low",
                "claim": "多段经历使用相似业绩句式结构",
                "issue": "描述结构高度同质化，常见于简历模板或机构统一包装",
                "recommendation": "建议要求候选人展开其中一段的完整上下文。",
                "clarification_questions": [
                    "能否详细还原其中一个项目的决策过程与您的具体动作？",
                ],
            }
        )

    return findings


def _extract_clarification_context(resume_json: dict) -> List[dict]:
    """候选人已回复的招聘方澄清，作为审计时的补充上下文。"""
    return list((resume_json or {}).get("clarification_answers") or [])[-5:]


def _apply_clarification_mitigation(findings: List[dict], resume_json: dict) -> List[dict]:
    """
    若候选人已通过澄清说明回应相关疑点，降级 severity，更贴近人类复核思路。
    """
    clarifications = _extract_clarification_context(resume_json)
    if not clarifications:
        return findings

    answer_blob = " ".join(
        f"{c.get('claim_text', '')} {c.get('answer', '')}" for c in clarifications
    ).lower()
    if not answer_blob.strip():
        return findings

    wording_categories = {"职责合理性", "表述模糊点", "语义模糊/包装词", "职责边界"}
    mitigated: List[dict] = []
    for f in findings:
        item = dict(f)
        claim = (item.get("claim") or "").lower()
        issue = (item.get("issue") or "").lower()
        category = item.get("category") or ""

        claim_overlap = claim and any(
            claim[i : i + 4] in answer_blob for i in range(max(0, len(claim) - 3))
        )
        addressed = claim_overlap or any(
            kw in answer_blob
            for kw in ("开发", "负责", "团队", "框架", "产品", "项目", "贡献", "角色")
            if kw in issue or kw in claim
        )

        if addressed and category in wording_categories:
            sev = item.get("severity", "medium")
            if sev == "high":
                item["severity"] = "medium"
            elif sev == "medium":
                item["severity"] = "low"
            item["mitigated_by_clarification"] = True
            item["recommendation"] = (
                (item.get("recommendation") or "")
                + "（候选人已提供补充说明，建议结合对话内容复核，勿仅凭简历措辞下结论。）"
            ).strip()

        mitigated.append(item)
    return mitigated


def _downgrade_wording_only_findings(findings: List[dict]) -> List[dict]:
    """
    将「期望职位 vs 经历描述」「技能标签不全」等表述类信号默认降级。
    真实招聘官通常会先追问，而非直接标 high。
    """
    wording_markers = (
        "期望职位",
        "意向职位",
        "技能标签",
        "表述",
        "措辞",
        "描述涉及",
        "缺少技术",
        "职责涉及",
        "产品经理",
        "开发工程师",
    )
    adjusted: List[dict] = []
    for f in findings:
        item = dict(f)
        issue = item.get("issue") or ""
        if any(m in issue for m in wording_markers):
            if item.get("severity") == "high":
                item["severity"] = "medium"
            item["signal_type"] = "wording"
            if not item.get("possible_explanations"):
                item["possible_explanations"] = [
                    "可能是全栈/创业项目中兼做产品与开发",
                    "可能是简历按成果写而非按岗位模板写",
                    "可能是技能栏未更新但经历中已体现能力",
                ]
        else:
            item.setdefault("signal_type", "consistency")
        adjusted.append(item)
    return adjusted


def _run_role_mismatch_rules(resume_json: dict, job_json: Optional[dict]) -> List[dict]:
    """规则版职责-title 不匹配（技术岗写产品活、产品写架构等）。"""
    findings: List[dict] = []
    tech_signals = (
        "分库分表",
        "服务治理",
        "微服务",
        "K8s",
        "Redis",
        "MySQL",
        "架构设计",
        "P99",
        "QPS",
    )
    pm_signals = ("需求分析", "用户调研", "PRD", "路线图", "竞品分析")

    for exp in resume_json.get("work_experience") or []:
        if not isinstance(exp, dict):
            continue
        title = (exp.get("position") or exp.get("title") or "").lower()
        desc = exp.get("description") or ""
        if not desc:
            continue

        is_pm_title = any(k in title for k in ("产品", "product", "pm"))
        is_eng_title = any(
            k in title for k in ("开发", "工程师", "engineer", "后端", "前端", "架构")
        )

        tech_in_desc = sum(1 for s in tech_signals if s in desc)
        pm_in_desc = sum(1 for s in pm_signals if s in desc)

        if is_pm_title and tech_in_desc >= 3:
            findings.append(
                {
                    "category": "职责合理性",
                    "severity": "low",
                    "signal_type": "wording",
                    "claim": f"{exp.get('company')} · {exp.get('position')}",
                    "issue": "职位为产品方向，但描述含大量后端/架构/engineering 职责",
                    "recommendation": "建议追问其在需求、方案、协调与研发之间的具体分工。",
                    "clarification_questions": [
                        "技术方案是您设计还是研发团队设计？您的具体产出物是什么？",
                    ],
                    "possible_explanations": [
                        "技术型产品经理或全栈负责人兼做方案与研发协调",
                        "职位名称偏产品但实质为技术主导",
                    ],
                }
            )
        if is_eng_title and pm_in_desc >= 3 and tech_in_desc == 0:
            findings.append(
                {
                    "category": "职责合理性",
                    "severity": "low",
                    "signal_type": "wording",
                    "claim": f"{exp.get('company')} · {exp.get('position')}",
                    "issue": "职位为技术方向，但描述偏产品/需求，缺少技术实现细节",
                    "recommendation": "建议追问技术栈、代码/设计贡献与个人产出。",
                    "clarification_questions": [
                        "您在该项目中具体写了哪些模块/接口？使用了什么技术栈？",
                    ],
                    "possible_explanations": [
                        "自研平台/创业项目中开发者兼做产品规划与功能设计",
                        "描述侧重业务成果，技术细节在其他 bullet 中",
                    ],
                }
            )

    return findings


def _semantic_llm_analysis(
    resume_json: dict,
    job_json: Optional[dict],
    existing_findings: List[dict],
) -> tuple[List[dict], dict]:
    """可选 LLM 软判断。"""
    metering = {
        "model_called": False,
        "provider_status": None,
        "provider_usage": None,
        "model_output_used": False,
    }
    if not os.getenv("DEEPSEEK_API_KEY"):
        return [], metering

    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    job_ctx = ""
    if job_json:
        job_ctx = f"目标岗位 JD：{json.dumps(job_json, ensure_ascii=False)[:2000]}"

    prompt = f"""你是一位有 10 年经验的招聘经理，正在做「履历可验证性」初审——不是刑侦式找造假。

## 你的思考方式（请模拟人类大脑活动）
1. **先信后疑**：默认候选人说的是真的，只在出现「逻辑硬冲突」时才提高严重度。
2. **区分两类问题**：
   - signal_type=wording（表述问题）：职位名称/期望岗位/技能栏 与 经历描述 的「写法不一致」，但可能是同一段真实经历的不同侧面。
   - signal_type=consistency（一致性问题）：时间线重叠、职级与年限明显矛盾、指标无口径等。
3. **期望职位 ≠ 历史经历标签**：候选人投 Java 开发，不代表过往项目不能写产品规划——尤其在自己搭建的平台/创业项目中，开发兼产品很常见。
4. **技能栏不全 ≠ 不会**：很多人把能力写在项目描述里，技能标签只填了部分，这应标为 low/medium 的「证据待补全」，不是 high。
5. **已有澄清说明时**：若候选人已回复过相关说明，应显著降级或不再重复追问。

{job_ctx}

简历摘要（含已保存的澄清回复 clarification_answers）：
{json.dumps(resume_json, ensure_ascii=False)[:6000]}

已有规则发现（勿重复）：{json.dumps([f.get("issue") for f in existing_findings[:5]], ensure_ascii=False)}

输出 JSON 数组，每项含：
category, severity(high/medium/low), signal_type(wording|consistency|evidence_gap),
claim, issue, recommendation,
possible_explanations(数组，列出 2~3 种合理真实解释),
clarification_questions(数组)

规则：
- 表述/角色边界类默认 severity 最高 medium，除非有时间线硬冲突
- 禁止直接指控造假
- 最多 3 条，只输出 JSON 数组
"""
    try:
        metering["model_called"] = True
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你只输出合法 JSON 数组。不指控造假。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        metering["provider_status"] = "succeeded"
        metering["provider_usage"] = extract_provider_usage(
            resp,
            provider="deepseek",
            requested_model=model,
        )
        content = (resp.choices[0].message.content or "[]").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        items = json.loads(content)
        if isinstance(items, list):
            metering["model_output_used"] = True
            return items[:3], metering
    except Exception as e:
        metering["provider_status"] = "failed"
        logger.warning("LLM credibility analysis failed: %s", e)
    return [], metering


def _overall_status(score: int, findings: List[dict]) -> str:
    high = sum(1 for f in findings if f.get("severity") == "high")
    wording_only = (
        all(
            f.get("signal_type") == "wording" or f.get("severity") in ("low", "medium")
            for f in findings
        )
        if findings
        else True
    )
    # 仅表述类疑点、无 hard high 时，不上升到人工复核
    if high >= 2 or (score >= 60 and not wording_only):
        return "manual_review"
    if score >= 30 or findings:
        return "needs_clarification"
    return "clear"


def build_credibility_report(
    resume_json: dict,
    job_json: Optional[dict] = None,
    *,
    include_llm: bool = True,
) -> dict:
    """
    生成招聘方看的履历可信度/一致性报告。
    """
    events = extract_timeline_events(resume_json or {})
    timeline_display = [
        {
            "type": e["type"],
            "label": e["label"],
            "start": f"{e['start'][0]}.{e['start'][1]:02d}" if e.get("start") else "未知",
            "end": f"{e['end'][0]}.{e['end'][1]:02d}" if e.get("end") else "未知",
        }
        for e in events
    ]

    findings: List[dict] = []
    findings.extend(_run_timeline_rules(events))
    findings.extend(_run_seniority_rules(resume_json, events))
    findings.extend(_run_packaging_and_template_rules(resume_json))
    findings.extend(_run_role_mismatch_rules(resume_json, job_json))

    metering = {
        "model_called": False,
        "provider_status": None,
        "provider_usage": None,
        "model_output_used": False,
    }
    if include_llm:
        llm_findings, metering = _semantic_llm_analysis(
            resume_json,
            job_json,
            findings,
        )
        seen_issues = {f.get("issue") for f in findings}
        for item in llm_findings:
            if item.get("issue") not in seen_issues:
                findings.append(item)

    findings = _downgrade_wording_only_findings(findings)
    findings = _apply_clarification_mitigation(findings, resume_json)

    # 去重
    deduped: List[dict] = []
    seen: set = set()
    for f in findings:
        key = (f.get("category"), f.get("issue"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    risk_score = compute_risk_score(deduped)
    status = _overall_status(risk_score, deduped)

    all_questions: List[str] = []
    for f in deduped:
        all_questions.extend(f.get("clarification_questions") or [])

    resume_blob = json.dumps(resume_json, ensure_ascii=False)
    template_count = len(detect_template_phrases(resume_blob))
    packaging_count = len(detect_packaging_in_text(resume_blob))

    from .claim_reasoning import reason_about_claims

    claim_reasoning = reason_about_claims(resume_json, job_json)
    combined_risk_score = max(risk_score, claim_reasoning.get("risk_score", 0))

    combined_status = status
    if claim_reasoning.get("flagged_claims", 0) > 0 and combined_status == "clear":
        combined_status = "needs_clarification"
    if combined_risk_score >= 60:
        combined_status = "manual_review"

    claim_questions: List[str] = []
    for pack in claim_reasoning.get("interview_question_pack") or []:
        claim_questions.extend(pack.get("questions") or [])

    unique_q = list(dict.fromkeys(all_questions + claim_questions))[:10]

    return {
        "overall_status": combined_status,
        "overall_status_label": STATUS_LABELS.get(combined_status, combined_status),
        "risk_score": combined_risk_score,
        "work_years_estimate": estimate_work_years(events),
        "timeline": timeline_display,
        "findings": deduped,
        "clarification_questions": unique_q,
        "homogeneity_signals": {
            "template_phrase_count": template_count,
            "packaging_word_count": packaging_count,
            "note": "模板句/包装词偏多可能来自机构统一包装，需面试验证细节",
        },
        "claim_reasoning": claim_reasoning,
        "disclaimer": (
            "本报告仅用于履历一致性与可验证性审查，不构成造假判定。"
            "标为「表述问题」的信号通常可通过澄清或忠实改写优化简历措辞；"
            "最终结论需结合面试、候选人说明、证明材料与正式背调。"
        ),
        "_metering": metering,
    }

# C6 Consented Pilot Protocol / C6 经同意的真实用户试点协议

> Status: protocol ready; recruitment and data collection have not started. This is an exploratory product pilot, not hiring research and not evidence of employment outcomes.

## 1. Question / 研究问题

Can an evidence-grounded workflow help early-career candidates produce a useful, source-supported application plan faster than an unstructured general-assistant workflow, while keeping unsupported facts and consequential actions under user control?

证据驱动的结构化工作流，能否比通用对话式助手更快帮助早期职业用户形成有用且有来源的申请计划，同时不把未经支持的内容或高影响操作交给系统自动执行？

## 2. Participants and scope / 用户与范围

- Recruit 20 students, new graduates, or candidates with no more than three years of full-time experience.
- Each participant brings one real target JD and at least two real experiences they are comfortable using for the session.
- Do not recruit the project maintainer as a measured participant.
- Do not collect protected attributes for ranking or subgroup scoring.
- Exclude any session where the participant cannot give informed consent or needs the platform to submit an application on their behalf.

目标是 20 名学生、应届生或全职工作三年以内的求职者。每人使用一份真实目标 JD 和至少两段愿意用于试点的真实经历。维护者本人不能作为计量样本；不采集受保护属性做排序或分组评分；试点不代替用户投递。

## 3. Consent and data handling / 同意与数据处理

Before the session, explain:

1. QLink is a pilot and may make mistakes.
2. AI suggestions are drafts, not verified facts or hiring predictions.
3. Participation is voluntary and can stop at any time.
4. A participant may use redacted material and may withdraw uploaded evidence.
5. No resume, JD, evidence, transcript, or outcome will be committed to GitHub.
6. Only de-identified aggregate metrics may be published.
7. External submission, messaging, or account actions remain outside the pilot.

Consent must be recorded separately from product analytics. A participant identifier must be a random pilot ID, not an email, name, student ID, or platform user ID in the analysis file.

## 4. Study design / 试点设计

This is a small exploratory comparison, not a powered causal study.

- Randomly assign 10 participants to start with QLink and 10 to start with a general-assistant baseline.
- Both conditions receive the same task: use the participant’s JD and chosen experiences to produce a requirement map, a prioritized application plan, and one interview story outline.
- Record the first condition as the primary time-to-output observation.
- After the primary rating, allow an optional crossover so every participant can compare both approaches; label crossover observations separately because learning effects make them non-independent.
- Use the same written success criteria and stop clock in both conditions.
- Do not let the evaluator silently fix an output before the participant rates it.

通用助手基线必须使用同一份输入与任务，但不使用 QLink 的结构化证据状态。试点记录工具与顺序，不把两种条件产生的内容混成一个结果。

## 5. Session tasks / 单次任务

1. Review consent and choose what material may be used.
2. Import or paste one target JD.
3. Add at least two experiences and optional evidence.
4. Produce a requirement-to-evidence map.
5. Identify what is ready, what needs clarification, constraints, and at most two hypotheses per unresolved item.
6. Produce one user-reviewed resume/application change.
7. Produce one structured interview story outline.
8. Rate usefulness and identify every unsupported or misleading statement.
9. Decide whether to adopt, edit, or reject the output.
10. Receive a seven-day follow-up that asks only about product behavior—not hiring success.

## 6. Pre-registered measurements / 预先登记指标

### Primary value measures

| Measure | Definition |
|---|---|
| First useful output | Minutes from task start until the participant rates one output at least 4/5 and says it can be used after review |
| Supported adoption | Participant adopts or edits at least one suggestion whose source is visible and traceable |
| Interview completion | Participant completes one target-specific structured interview outline or session |
| Seven-day second behavior | Participant returns to review another JD, evidence item, interview, application, or outcome within seven days |

### Safety and quality measures

| Measure | Definition |
|---|---|
| Unsupported fact shown | Output states a candidate fact that is absent from candidate-provided sources |
| Unsupported fact saved | Such a statement reaches a saved resume version or confirmed Claim |
| Wrong route | A missing item is presented as a capability verdict rather than clarification/hypothesis |
| Unauthorized action | Submission, message, rejection, or external action occurs without preview and explicit approval |
| Source comprehension | Participant can correctly explain where a selected suggestion came from |

### Commercial signal

Ask a neutral willingness-to-pay question after the task and record whether the participant would join a paid follow-up at a stated price. Do not record “payment” unless money was actually collected through an authorized flow. A free pilot, discount, or hypothetical answer is not revenue.

## 7. Go / Iterate / Stop rules

Evaluate only after attempting all 20 sessions. Report completion and missingness; do not replace dropouts until their reasons are documented.

### Safety gate—required for any Go decision

- zero unauthorized high-impact actions;
- zero cross-user access incidents;
- zero unsupported candidate facts saved as confirmed material;
- every observed unsupported draft is counted and reviewed before release.

### Value gates

1. at least 70% of completed participants reach a useful output within 20 minutes;
2. at least 60% adopt or meaningfully edit one source-backed suggestion;
3. at least 50% complete the target-specific interview task;
4. at least 40% perform a genuine second behavior within seven days.

Decision:

- **Go:** safety gate passes and at least three of four value gates pass.
- **Iterate:** safety gate passes and exactly two value gates pass, or qualitative evidence identifies one concentrated, fixable bottleneck.
- **Stop / redesign:** a safety gate fails, fewer than two value gates pass, or participants cannot distinguish evidence from model suggestions.

The 20-person pilot is too small for broad statistical or fairness claims. Report counts, denominators, medians, ranges, missing data, and representative de-identified failure patterns—not p-values or hiring lift.

## 8. Minimal analysis record / 最小分析记录

Keep the analysis table outside the public repository. It may contain only:

```text
pilot_id
consent_version
assigned_first_condition
session_completed
time_to_first_useful_output_minutes
useful_output_rating_1_to_5
source_backed_change_adopted
interview_task_completed
unsupported_draft_count
unsupported_saved_count
wrong_route_count
unauthorized_action_count
source_comprehension_passed
seven_day_second_behavior
willing_to_pay_at_stated_price
withdrawn
```

Free-text notes must be de-identified before analysis. Do not put resume text, company names, URLs, interview transcripts, emails, or uploaded artifacts in this table.

## 9. Reporting template / 报告模板

Publish only after the pilot:

- recruitment dates and eligible/completed/withdrawn counts;
- condition assignment and crossover counts;
- each metric’s numerator, denominator, median/range where applicable;
- every safety incident and remediation;
- top three observed failure patterns;
- Go / Iterate / Stop result with the pre-registered rule;
- limitations and deviations from this protocol;
- explicit statement that the pilot does not measure hiring probability or employment outcomes.

Until those data exist, public documentation must continue to say: **protocol ready; recruitment pending; no real-user effectiveness claim.**

## 10. Neutral recruitment message / 中立招募文案

> 你好，我正在测试一个帮助学生和早期职业求职者把真实经历对应到目标岗位的工具。试点会使用你自己选择的一份岗位描述和至少两段愿意分享的经历，预计 45–60 分钟，并在七天后进行一次很短的回访。工具不会替你投递，也不会把 AI 建议当成已验证事实。参与完全自愿，可以使用删减材料，也可以随时停止或撤回。我们只公开去标识化的汇总结果，不会把简历、岗位、证据或对话上传到 GitHub。如果你符合学生、应届生或全职工作三年以内，并愿意参加，请回复你的可用时间；详细同意说明会在开始前单独提供。

Recruitment must not promise a better job, improved hiring probability, free application submission, or privileged employer access. Do not pressure classmates, employees, applicants, or people whose relationship to the maintainer makes refusal difficult.

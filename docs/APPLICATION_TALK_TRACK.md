# QLink Application and Interview Talk Track / QLink 申请与面试表达

> Use only statements you can personally explain. Replace bracketed fields with truthful personal context. Do not claim external validation, real-user effectiveness, revenue, or hiring lift until the corresponding evidence exists.

## 60-second English version

I am building QLink, an evidence-grounded job decision and application workflow for students and early-career candidates. I started from a human problem: people often cannot tell which of their real experiences support a role, while generic AI tools can make polished suggestions without making uncertainty visible.

I designed the system to separate candidate-provided evidence, missing information, real-world constraints, and development actions. It is a full-stack FastAPI and React application with PostgreSQL migrations, ownership controls, idempotent writes, user-reviewed resume versions, structured interview practice, and outcome tracking. Consequential actions stay under human approval, and model output does not become a candidate fact automatically.

I also treated ranking as an experiment rather than a magic score. On a fixed synthetic dataset, I compared TF-IDF/cosine similarity with a structured, preference-aware ranker, measured relevance and cross-career-family failures, and kept a documented baseline failure where text similarity ignored an industry exclusion. The next step is not a larger model; it is independent annotation and a consented 20-person pilot with pre-registered safety and value gates.

This project taught me that responsible engineering is not only about model accuracy. It is about designing who can decide, what evidence supports a conclusion, how a failure is measured, and when a team should stop or redesign.

## 中文 60 秒版本

我在做 QLink，一个面向学生和早期职业求职者的证据驱动求职决策与申请准备系统。项目起点是一个人本问题：很多人不知道自己的哪些真实经历能够支持某个岗位，而通用 AI 虽然能生成流畅建议，却常常没有把信息缺口和不确定性展示出来。

我把系统设计成明确区分候选人提供的证据、待确认信息、现实约束和发展行动。它是一个 FastAPI + React 全栈项目，包含 PostgreSQL 迁移、资源所有权、幂等写入、用户确认的简历版本、结构化面试和结果追踪。高影响操作始终需要人工确认，模型输出不会自动变成候选人事实。

在排序上，我没有只做一个看起来很聪明的总分，而是做了可复现实验：在固定合成数据集上比较 TF-IDF/cosine 和结构化偏好排序，衡量相关性、跨职业族错误、引用覆盖和反事实稳定性，并保留了纯文本方法无法遵守行业排除偏好的失败案例。下一步不是马上训练更大的模型，而是完成独立双人标注和一个预先登记安全与价值门槛的 20 人真实试点。

这个项目让我理解，负责任工程不只是提高模型准确率，还包括谁拥有最终决定权、结论由什么证据支持、失败如何被测量，以及什么时候应该停止或重新设计。

## Three interview stories / 三个面试故事

### 1. Technical judgment: preserve a failure

- **Situation:** the structured ranker placed a backend role in a product candidate’s Top 3.
- **Task:** reduce irrelevant cross-family recommendations without hiding the sample or padding results.
- **Action:** traced the error to an overly broad adjacent-family policy; required at least two cited overlapping skills; reran the fixed set.
- **Result:** measured cross-family violation at K=3 moved from `0.111` to `0.000` on this small synthetic dataset; the system returned two supported roles instead of inventing a third.
- **Learning:** a smaller, explainable result can be better than a cosmetically full ranking.

### 2. Responsible product decision: hypothesis is not fact

- **Situation:** missing resume text was being discussed as though it might indicate missing capability.
- **Task:** let the system be useful under uncertainty without silently labeling the candidate.
- **Action:** introduced a five-state route and a separate hypothesis object, capped at two per issue, with source, version, status, ownership, and confirm/reject actions.
- **Result:** automated tests demonstrate that confirming a hypothesis creates no Claim, changes no resume, and changes no hiring conclusion.
- **Learning:** useful inference needs a reversible state transition, not just cautious wording.

### 3. Leadership and experimentation: resist premature scale

- **Situation:** competitor research suggested social networking, enhanced profiles, and recommendation feeds.
- **Task:** decide what to build without copying a mature platform’s entire engagement model.
- **Action:** adopted modular profile, reversible enhancement, preference-aware recommendations, and feedback refresh; deferred Feed, likes, public contact graphs, and autonomous submission until retention evidence exists; published a consented pilot protocol and explicit Go / Iterate / Stop gates.
- **Result:** the roadmap now ties expansion to measured user behavior and safety, not feature parity.
- **Learning:** leadership includes choosing what not to build and making the next decision falsifiable.

## Honest evidence table

| Safe to say now | Do not say yet |
|---|---|
| Runnable full-stack pilot Demo | Production ATS used at scale |
| Fixed synthetic ranking evaluation | Proven real-world hiring improvement |
| Author labels plus independent-review tooling | Externally validated labels (`pending 0/2`) |
| Counterfactual checks for synthetic name/school changes | The system is fully fair |
| Browser journeys pass in an isolated test stack | Bug-free in every environment |
| C6 protocol and recruitment copy are ready | 20-user pilot completed |
| Commercial dual-license path documented | Paying customers or revenue |

## Likely follow-up questions

### Why not train a neural model or use PyTorch now?

The current bottleneck is not model capacity. It is label quality, real-user validation, and product-policy errors such as preference conflicts. A more complex model would make those problems harder to diagnose. Embeddings or learned ranking become appropriate only after independent labels and a larger consented evaluation set justify them.

### Is education part of ranking?

Only an explicit job-level requirement may be represented as a reality constraint. School identity and prestige are prohibited signals. The counterfactual evaluation changes synthetic school names while holding relevant inputs fixed and expects unchanged rankings.

### Why not automatically submit applications?

Submission is consequential, brittle across third-party forms, and can create incorrect statements or unwanted employer contact. QLink may prepare or prefill a reviewable draft, but external submission remains previewed and explicitly approved. The current MVP does not autonomously submit.

### What did AI tools contribute?

AI tools assisted implementation, test generation, debugging, and documentation. Human responsibility remained with product scope, safety invariants, architecture decisions, acceptance criteria, reviewing changes, and deciding what evidence supports a claim. Describe the specific code and trade-offs you personally understand; do not imply unaided authorship.

### What would make you stop the project?

The published C6 protocol calls for stopping or redesigning if a safety gate fails, fewer than two of four value gates pass, or users cannot distinguish evidence from model suggestions. This is intentionally stated before data collection.

## Program adaptation

- **Emerging leadership:** emphasize the human problem, the decision boundaries, inviting independent review, and Go / Iterate / Stop responsibility.
- **Engineering:** emphasize ownership, idempotency, migrations, model-off degradation, test isolation, and full-chain browser verification.
- **Data/ML:** emphasize fixed data, baseline comparison, graded relevance, NDCG/Recall, robustness failures, counterfactual checks, and label uncertainty.
- **Fintech:** emphasize auditability, explicit user preferences, evidence lineage, consequential-action approval, and refusal to translate weak signals into opaque human scores.
- **Entrepreneurship/product:** emphasize competitor synthesis, what was intentionally deferred, adoption/retention gates, and a realistic commercial licensing path.

Always verify current program eligibility and deadlines from the official program page before adapting this material.

# Ranking Annotation Protocol / 排序标注协议

## 中文

### 状态与目的

当前 `ranking_eval_v1.json` 中的分级相关性是项目作者参考标签，**不是已经完成的独立双人标注**。截至当前，独立复核状态为 `pending`，完成人数为 `0/2`。

本协议的目标是让两名复核者在不看模型排名、分数或对方答案的情况下，独立标注每个合成候选人–岗位对，然后量化一致性并保留分歧。

### 盲标流程

1. 为两名复核者使用不同别名和不同随机种子生成空白模板；
2. 只向复核者提供固定数据集、本协议和本人的空白模板；
3. 不提供 TF-IDF/结构化排名、评测指标、作者参考标签或另一名复核者文件；
4. 复核者标注所有候选人–岗位对，并为每条记录至少一个依据字段；
5. 完成后将 `independent_review_attestation` 设为 `true`；
6. 先分别执行 `validate`，再执行 `compare`；
7. 对所有分歧进行裁决，保留两份原始标注和裁决理由。

### 相关性等级

| 等级 | 定义 | 不允许的解读 |
|---:|---|---|
| 0 | 与当前目标明显无关，或命中必须排除的职业族/用户明确排除条件 | 不表示候选人“差”或无法胜任其他岗位 |
| 1 | 弱相关或探索性方向，有少量可迁移元素，但不应作为主推荐 | 不是录用概率 |
| 2 | 相关：目标、任务或多项技能有可引用的对应 | 不是系统已证实能力 |
| 3 | 高度相关：目标职业族一致，且核心任务/技能有多个直接对应 | 不是“最适合候选人”结论 |

`forbidden_cross_family=true` 时，`relevance` 必须为 0。“简历未写”不能单独成为 forbidden 理由；该情况只能记录为信息待确认。

### 可使用与禁止使用的依据

可使用：候选人明确目标、已写技能、经历/项目任务、用户偏好、岗位职责、岗位要求和现实约束。

禁止使用：姓名、学校或前雇主品牌声望、保护属性或代理变量、“像不像优秀候选人”的主观感受、录用可能性推测。

### 生成、校验和比较

```bash
make ranking-label-template REVIEWER_ALIAS=reviewer-a SEED=101 \
  > /tmp/qlink-reviewer-a.json
make ranking-label-template REVIEWER_ALIAS=reviewer-b SEED=202 \
  > /tmp/qlink-reviewer-b.json

backend/.venv/bin/python backend/scripts/ranking_annotations.py validate \
  --annotation /tmp/qlink-reviewer-a.json
backend/.venv/bin/python backend/scripts/ranking_annotations.py validate \
  --annotation /tmp/qlink-reviewer-b.json

make compare-ranking-labels \
  REVIEWER_A=/tmp/qlink-reviewer-a.json \
  REVIEWER_B=/tmp/qlink-reviewer-b.json \
  > /tmp/qlink-annotation-comparison.json
```

空白模板不能通过完整性校验。工具要求两个不同别名、完整覆盖所有数据对、合法的 0–3 等级、布尔型 forbidden 标签和至少一个依据字段。

### 一致性和发布门禁

工具输出：

- 精确相关性一致率；
- 适合 0–3 有序等级的二次加权 Cohen’s kappa；
- forbidden 标签一致率；
- 包含双方依据和待裁决字段的分歧清单。

公开“已独立复核”前，建议门禁为：精确一致率至少 0.75，加权 kappa 至少 0.70，forbidden 一致率必须 1.00，所有分歧已裁决。未达标时先改进协议和标签定义，不删除“难标”样本来制造高一致率。

### 独立复核邀请模板

> 你好，我在为一个证据驱动的求职决策项目做小型排序评测，希望邀请你独立标注 33 个完全合成的候选人–岗位对。任务不涉及真实简历或招聘决定，预计需要 30–45 分钟。你会收到随机顺序的空白模板和标注规则，但不会看到模型排名、项目作者标签或另一名复核者的答案。完成后我会先比较一致性，再对分歧进行讨论；不会为了提高分数删除分歧样本。参与完全自愿。如果你愿意，请只回复是否可以参加，我再单独发送材料。

邀请时不要把作者标签、当前指标、期望结论或另一位复核者身份放进消息。两名复核者必须分别提交原始文件，不能协作填写。

## English

The current relevance grades are author reference labels. Independent review is honestly marked `pending` at `0/2`; no external reviewers are claimed.

Two reviewers must receive differently shuffled blank templates and work without model scores, rankings, reference labels, or each other’s files. Every pair requires a 0–3 relevance grade, a cross-family-forbidden boolean, and at least one cited source field. Missing resume information is uncertainty, not proof of inability.

The comparison tool reports exact agreement, quadratic-weighted Cohen’s kappa, forbidden-label agreement, and adjudication-ready disagreement records. Before claiming independent review, the recommended gates are exact agreement ≥ 0.75, weighted kappa ≥ 0.70, forbidden agreement = 1.00, and all disagreements adjudicated.

Names, school or employer prestige, protected attributes or proxies, subjective candidate quality, and hiring-probability assumptions are prohibited annotation inputs.

Suggested invitation:

> I am evaluating an evidence-grounded job-decision project and am looking for an independent reviewer to label 33 fully synthetic candidate–job pairs. The task uses no real resumes or hiring decisions and should take about 30–45 minutes. You will receive a shuffled blank template and the annotation rules, but not model rankings, author labels, or another reviewer’s answers. I will compare agreement first and preserve disagreements for adjudication rather than deleting difficult samples. Participation is voluntary. If you are interested, please reply only with availability and I will send the materials separately.

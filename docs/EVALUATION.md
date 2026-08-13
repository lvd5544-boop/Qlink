# QLink Ranking Evaluation / QLink 排序评测

## 中文

### 目的

QLink 的岗位推荐是候选人的决策支持，不是录用概率或候选人质量评分。C4-E 评测用一个小型、固定、完全合成的数据集，比较两种方法：

1. `TF-IDF + cosine similarity` 文本基线；
2. 产品当前的 `structured_human_preference_v3` 结构化排序。

评测不访问数据库、不调用外部模型，也不包含真实简历、真实投递或雇主导出数据。

### 复现

在项目根目录执行：

```bash
make evaluate-ranking
```

如需保存机器可读结果：

```bash
backend/.venv/bin/python backend/scripts/run_ranking_evaluation.py \
  --output /tmp/qlink-ranking-eval-v1-results.json
```

固定数据集位于
`backend/evaluation_data/ranking_eval_v1.json`，评测逻辑位于
`backend/app/ranking_evaluation.py`。数据集版本为 `1.1.0`，评测器版本为 `c4-e-v1.3`。

### v1 结果

`K=3`，共 3 个合成候选人查询、11 个合成岗位、33 个候选人–岗位对。相关性标注为 0–3，其中 2 以上计入 Recall。

| 方法 | NDCG@3 | Recall@3 | 跨职业族违规率@3 | 无依据负面判断率 | 解释引用覆盖率 |
|---|---:|---:|---:|---:|---:|
| TF-IDF + cosine | 0.961 | 0.889 | 0.000 | 0.000 | 0.818 |
| Structured human preference v3 | 0.974 | 0.778 | 0.000 | 0.000 | 1.000 |

这些数字只说明两个排序器在当前小型合成集上的行为，不能外推为真实求职效果。指标仍可能被数据集规模和文本区分度高估，因此不能宣称基线或结构化排序已在真实世界充分有效。

v1.3 新增 `Technical Product Analyst`跨界近义岗位。作者参考标签将它对数据和产品方向都标为 2，但当前结构化职业分类没有稳定识别该混合职能，导致两个查询的漏召回。该标签在两名独立复核者完成盲标前不用于直接改动线上职业族政策。

### v1.2 鲁棒性压力测试

| 压力用例 | TF-IDF | 结构化排序 | 验证内容 |
|---|---|---|---|
| 中英文改写 | 通过 | 通过 | 中文经历改写后，Top 3 仍至少命中两个后端岗位 |
| 可选字段缺失 | 通过 | 通过 | 没有 summary、经历描述、项目和地点时仍安全降级 |
| 偏好与文本相似度冲突 | **未通过（预期基线局限）** | 通过 | 用户排除金融后，纯文本基线仍把支付后端排第一 |
| 近标题干扰岗位 | 通过 | 通过 | `Backend Operations Coordinator` 不得因标题含 backend 进入 Top 3 |

结构化排序 4/4 通过，TF-IDF 3/4 通过。TF-IDF 的失败是基线的能力边界：它可以比较文本，但不能将用户明确排除的行业当作选择政策。评测保留该失败，不把纯文本基线包装成完整推荐系统。

### 独立标注状态

- 作者参考标签：已完成；
- 要求的独立复核者：2 名；
- 已完成独立复核：0 名；
- 当前状态：`pending`。

不能在 GitHub 或项目申请中声称“已经外部独立验证”。空白盲标模板、加权 Cohen’s kappa、分歧记录和发布门禁见 [排序标注协议](./RANKING_ANNOTATION_PROTOCOL.md)。

### 反事实公平性

每个查询只更改合成姓名和合成学校名称，其他输入不变。两种方法均满足：

- 3/3 查询排序顺序完全不变；
- 最大分数差为 `0.0`；
- TF-IDF 明确不读取姓名、学校和雇主名称。

这不等于已经证明系统完全公平。v1 只覆盖两个字段和少量样本，后续需要增加地点、简历格式、文本风格和缺失信息等测试。

### 失败案例与修复

首次评测时，结构化排序在 `query-product` 的 Top 3 中把
`job-backend-fintech` 放在第 3 位，跨族违规率为 `0.111`。根因是偏好政策把广义“产品–软件”视为相邻方向，但没有要求具体任务或技能证据。

修复没有删掉样本，而是对“相邻职业族”增加至少两项可引用技能重合的门禁，并只统计候选人实际可见的 eligible 推荐。复验后跨族违规率为 `0.000`；`query-product` 只返回两个有依据的产品岗位，不为了凑满 Top 3 而加入后端岗位。

### What changed the ranking?

固定案例仅把后端候选人的首选行业从“金融/科技”改为“医疗”，技能、经历、项目和教育信息均不变。

- 变更前 Top 3：支付后端、云平台、医疗后端；
- 变更后只有两个可见结果：医疗后端、云平台；
- 医疗后端从第 3 升到第 1；
- 支付后端和金融数据分析因用户明确排除金融行业，离开可见推荐。

这个解释只说明哪个输入改变了顺序，不把偏好变化改写成候选人新的能力事实。

## English

### Purpose

QLink recommendations are decision support, not hiring probabilities or candidate-quality scores. C4-E compares a deterministic TF-IDF/cosine baseline with the current structured human-preference ranker on a fixed, fully synthetic dataset.

The evaluation runs offline, makes no external model calls, performs no database writes, and contains no real resumes, applications, or employer exports.

### Results and interpretation

At `K=3`, the set contains 3 synthetic candidate queries, 11 synthetic jobs, and 33 graded pairs. TF-IDF reaches NDCG@3 `0.961` and Recall@3 `0.889`; the structured ranker reaches NDCG@3 `0.974` and Recall@3 `0.778`.

The first structured run produced a cross-family violation rate of `0.111`: a backend role entered the third position for a product query. The sample remained fixed. Requiring at least two cited skill overlaps for an adjacent-role recommendation reduced the rerun violation rate to `0.000`; the product query now returns two supported roles instead of padding the list. This before/after result is more useful than a cosmetically perfect first score because it identifies and closes a falsifiable product boundary.

Changing only synthetic names and school names left every score and ordering unchanged in both methods. This is a narrow counterfactual check, not a general fairness guarantee.

Four robustness cases cover a Chinese paraphrase, missing optional fields, a preference/text conflict, and a near-title decoy. The structured ranker passed 4/4. TF-IDF passed 3/4 and intentionally remains red on the preference-conflict case: after the candidate excludes finance, text similarity still ranks the payments backend first. This is a documented baseline limitation, not a product-policy failure to hide.

The new cross-functional `Technical Product Analyst` pair exposes lower structured recall and is intentionally awaiting two independent blind reviews before it drives a taxonomy change. Current independent-review status is `pending` at `0/2`; the repository does not claim external validation.

### Limitations

- The dataset is intentionally small and synthetic.
- Labels describe relevance for product testing; they are not employer decisions or candidate-quality labels.
- High scores cannot be interpreted as real-world hiring performance.
- Counterfactual coverage is limited to name and school-name changes in v1.
- The next dataset version should add harder near-duplicate roles, multilingual paraphrases, missing fields, and additional preference conflicts.

# 可验证的简历优化流程与算法评测计划

> 状态：研究与实施方案，不是有效性声明。本文中的阈值是 QLink 的预注册工程门禁，
> 不是文献证明的通用行业标准。在完成盲标、离线评测和经同意的用户试点前，产品不得
> 声称能提高录用概率、通过 ATS 的概率或求职结果。

## 1. 结论

QLink 不应继续把一个固定权重的“匹配分”同时当成岗位理解、候选人能力、简历质量和
改写收益。可靠的优化对象应拆成六个可分别验证的任务：

1. 简历与 JD 解析是否忠实；
2. JD 要求是否有原文依据；
3. 候选人主张是否有本人确认的来源；
4. 要求与主张之间是否真的相关、支持或冲突；
5. 改写是否只改变表达而没有增加事实；
6. 用户是否理解来源并愿意采用该修改。

最终产品展示的是“要求—证据状态”和有来源的行动建议，而不是虚假的精确 ATS 分数。
任何总分只能作为同一版本规则下的导航摘要，并同时显示覆盖范围、未知项和规则版本。

## 2. 参考依据及其边界

### 2.1 岗位与技能标准化

- [O*NET Content Model](https://www.onetcenter.org/content.html) 将职业信息拆为任务、工作活动、技能、知识、教育、经验和工作情境等不同构念；适合定义数据结构和职业分析维度。
- [O*NET 31.0 数据字典](https://www.onetcenter.org/dictionary/31.0/csv/content_model_reference.html) 提供版本化变量与可下载数据，适合固定 taxonomy 版本并复现实验。
- [ESCO 使用说明](https://esco.ec.europa.eu/en/use-esco) 与 [ESCO API](https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/esco-api) 提供多语言、稳定 URI、职业—技能关系和版本化访问；适合中英文同义词归一和跨语言映射。

边界：O*NET/ESCO 只能做标准化和召回扩展，不能把 taxonomy 中常见的技能自动变成某家
公司的招聘要求。公司要求只能来自当前 JD 的可引用原文。

### 2.2 信息抽取与匹配基准

- Zhang et al., [SkillSpan: Hard and Soft Skill Extraction from English Job Postings](https://aclanthology.org/2022.naacl-main.366/)（NAACL 2022）发布了领域专家标注的 span-level 数据和标注指南，支持用 span precision/recall/F1 验证 JD 技能抽取，而不是只看 JSON 是否生成成功。
- Pezeshkpour et al., [Distilling Large Language Models using Skill-Occupation Graph Context for HR-Related Tasks](https://arxiv.org/abs/2311.06383) 发布 RJDB，覆盖技能/经历抽取、简历—JD 匹配、解释和简历编辑，可用于外部回归测试。

边界：RJDB 的大部分样本来自模型蒸馏，不能替代独立人工金标或真实用户验证；SkillSpan
主要是英文招聘文本，不能直接证明中文、简历 PDF 或 QLink 用户群上的性能。

### 2.3 有效性、代表性与公平性

- EEOC 的 [Employment Tests and Selection Procedures](https://www.eeoc.gov/laws/guidance/employment-tests-and-selection-procedures) 要求选择程序与具体岗位和用途相关，并在存在不利影响时考虑同样有效但影响更小的替代方案。
- [Uniform Guidelines 问答](https://www.eeoc.gov/es/node/130157) 区分 criterion、content 和 construct 三类有效性证据，并强调与实际工作内容之间的联系。
- SIOP 的 [Principles for the Validation and Use of Personnel Selection Procedures（第五版，2018）](https://www.apa.org/ed/accreditation/personnel-selection-procedures.pdf) 提供人员选择程序的开发和验证原则。
- Fritzsche & Brannick, [The Importance of Representative Design in Judgment Tasks: The Case of Resume Screening](https://digitalcommons.usf.edu/psy_facpub/2335/) 发现简化 profile 上的判断不能直接推广到真实简历判断；评测必须包含代表性的完整简历与版式。
- Weedon, [A Framework for Résumé Decisions](https://eric.ed.gov/?id=EJ1276494) 汇总学生、顾问和雇主作简历决策时使用的 relevance、recency、value 等理由，支持把建议做成可解释的局部决策，而不是万能格式规则。

边界：QLink 是候选人决策支持工具，不是雇主选择程序；以上原则用于提高验证质量和避免
越界声明，不表示产品已经满足任何司法辖区的全部法律要求。

### 2.4 生成式 AI 风险与文档化

- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) 及 [Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) 要求在设计、测量和使用阶段管理有效性、可靠性、可解释性、偏差与 confabulation 风险。
- Xin et al., [The Art of Abstention](https://aclanthology.org/2021.acl-long.84.pdf) 说明 NLP 系统可以对不确定样本拒答并交给人或更可靠流程；QLink 的 `unknown/clarify` 应是正式输出，不是异常路径。
- Mitchell et al., [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993) 与 Gebru et al., [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) 支持记录预期用途、数据来源、分组性能、限制和版本变化。

## 3. 建议的端到端产品流程

### 阶段 A：冻结输入与解析

输入：候选人拥有的简历、目标 JD、可选证据；输出：带内容哈希的不可变快照。

1. 解析 PDF/DOCX/TXT，同时保存原文 span、页码、字段置信度和解析器版本。
2. 将结构化结果回显给用户；低置信字段必须人工确认或保持 `unknown`。
3. 对生成后的简历再做一次“渲染 → 文本抽取 → 结构化解析”回环，检测内容丢失、乱序和 ATS 类解析失败。
4. 原始文件与已有版本永不被原地覆盖。

### 阶段 B：把 JD 拆成可引用要求

每条要求保存：`requirement_id`、原文 span、类型、must/preferred、否定/条件、重要性来源、
标准化 URI、taxonomy 版本和抽取置信度。

要求类型至少包括：任务、硬技能、知识、经验、资格/许可、地点/工时/签证等客观约束。
模型可以提取和归一，但不得根据 O*NET/ESCO 或论坛内容新增雇主要求。低置信或语义冲突时
进入人工复核。

### 阶段 C：建立原子 Claim 与证据账本

把简历句子拆成最小可核对主张，例如角色、动作、对象、方法、范围、结果和时间。每条 Claim
保留候选人来源、确认状态、证据状态、敏感性和撤回状态。

建议使用四级证据，而不是真假二元值：

- `E0 unconfirmed`：只由模型提出；
- `E1 candidate_stated`：候选人明确确认；
- `E2 artifact_supported`：关联候选人拥有且未撤回的材料；
- `E3 consistency_checked`：来源之间已做一致性检查，没有发现冲突。

这些级别表示来源强度，不表示第三方独立证明。任何冲突单独保存，不自动选择对系统最有利
的版本。

### 阶段 D：要求—证据映射

先用词法、taxonomy 同义词和语义召回取得候选 Claim，再用有监督的 pairwise 模型或严格
规则判定关系。每一对只能是：

- `supported`：现有 Claim 直接支持；
- `partial`：只覆盖部分范围或熟练度；
- `unknown`：材料没有说明；
- `conflict`：来源出现不一致；
- `not_applicable`：该要求不适用于当前路径。

`unknown` 绝不能改写成“不具备”。只有 JD 明确的 must 条件可以成为 blocker；preferred
项不得使用同样惩罚。模型置信度没有经过校准时，不对用户显示伪精确概率。

### 阶段 E：诊断与行动路由

诊断必须引用具体 requirement、Claim 和原文 span。按下列优先级给出下一步：

1. `ready_to_reframe`：已有 E1+ Claim，只需调整相关性、顺序或清晰度；
2. `clarify`：可能有经历但信息不足，生成至多两个具体问题；
3. `collect_evidence`：主张已确认但结果/范围需要材料支持；
4. `develop`：候选人明确选择未来学习或项目计划；
5. `constraint`：客观 must 条件单独处理；
6. `abstain`：来源冲突或置信度低，暂不建议改写。

“简介少于 40 字”“没有项目”“没有数字”只能触发检查，不能单独构成质量缺陷。某些岗位
不需要独立项目，某些贡献也不适合量化；数量必须有定义、基线、时间窗和个人贡献边界。

### 阶段 F：受约束的局部改写

1. 每次只改一个字段或一个 bullet；
2. 生成器只接收允许使用的 Claim/Evidence，不接收未映射的 JD 文本作为候选人事实来源；
3. 输出 `before`、`after`、原子 diff、每个新增片段的 Claim/Evidence 引用；
4. 自动阻止新增数字、实体、技能、头衔、范围、因果关系和最高级，除非它们有 E1+ 来源；
5. 执行 entailment/实体集合/数字集合/否定词/时间范围五类 Fidelity 检查；
6. 用户逐条采用、编辑或拒绝；编辑后再次检查；
7. 只有显式确认后才创建子版本，永不自动投递。

改写目标依次是：事实忠实、岗位相关、可读、简洁。关键词覆盖不能凌驾于事实忠实之上，
也不能通过机械重复关键词获得更高分。

### 阶段 G：版式与导出验证

分别验证语义和版式：关键字段解析召回、日期和条目归属、页面溢出、字体可读性、链接、
表格/多栏导致的读取顺序。输出“本系统回环解析结果”，不要输出“保证通过 ATS”。

### 阶段 H：反馈与可逆学习

记录 suggestion 的采用/编辑/拒绝、拒绝理由、解析失败和错误类型，但不把采用率直接当成
事实正确率。用户反馈只更新下一版策略；旧版本、规则版本和决策轨迹保持可重放。

## 4. 算法结构

建议用状态向量替代一个混合总分：

```text
coverage = weighted_supported_requirements / observable_requirements
unknown_rate = unknown_requirements / all_requirements
evidence_strength = distribution(E0, E1, E2, E3)
constraint_state = pass | unknown | conflict | fail
rewrite_eligibility = ready | clarify | evidence | develop | abstain
confidence = calibrated extraction/mapping confidence, not LLM self-rating
```

权重只允许来自当前 JD 中 must/preferred 和明确强调程度；初始规则不要学习历史录用结果，
因为它容易混入既有偏差、雇主品牌和受保护属性代理。若将来学习权重，训练目标应优先使用
独立标注的 requirement relevance、source-backed usefulness 和用户纠错，而不是“是否被录用”。

匹配推荐使用可消融的三段式架构：

```text
exact/span match + taxonomy aliases
        -> semantic candidate retrieval
        -> pairwise relation classifier with abstention
```

所有阶段都返回 source IDs；任一阶段丢失 provenance，最终改写就不具备保存资格。

## 5. 离线金标与指标

### 5.1 数据集

建立版本化的合成/经授权去标识数据集，按职业族、语言、资历、文件格式和版式分层；同一人的
版本不得跨 train/dev/test。首个可用版本建议至少包含 200 个 JD—简历组合和 1,000 条
requirement—Claim pair；这个数量是工程起点，不足以支持广泛公平性声明。

两名不了解模型输出的标注者独立标注，先验证指南，再计算有序标签的加权 Cohen's kappa，
保留全部分歧并裁决。合成集用于安全回归；代表性完整简历集用于外部有效性检查，两者的结果
不得混报。

### 5.2 预注册门禁

| 子任务 | 主要指标 | 首版发布门禁 |
|---|---|---|
| 简历/JD span 抽取 | strict span F1、field accuracy | macro F1 ≥ 0.90，关键约束 recall ≥ 0.98 |
| taxonomy 归一 | top-1 accuracy、unmapped rate | accuracy ≥ 0.90，并允许 unmapped |
| requirement—Claim 关系 | macro F1、`unknown` recall、混淆矩阵 | macro F1 ≥ 0.85，unknown recall ≥ 0.95 |
| 排序 | nDCG@5、Recall@5、bootstrap 95% CI | 相对词法基线改善，且 CI 不显示明显退化 |
| Fidelity | unsupported atomic claim rate、数字/实体新增率 | 保存版本均为 0；草稿 < 1%，且全部拦截 |
| 解析回环 | 关键字段 recall、条目顺序一致率 | 关键字段 ≥ 0.98，无静默丢失 |
| 公平/鲁棒性 | counterfactual invariance、分组错误率 | 禁止字段变化不改变建议；差异需逐项说明 |
| 标注可靠性 | weighted kappa、分歧裁决 | kappa ≥ 0.70，全部分歧已裁决 |

零门禁适用于“未经支持的事实被保存”和“未经批准的高影响操作”；其他阈值应在 pilot 前冻结，
不能看到测试结果后修改。所有比率同时报告分子、分母、置信区间和失败样例。

### 5.3 必须包含的压力测试

- 中英文释义、技能别名、缩写和大小写；
- `C`/`C++`、`Java`/`JavaScript` 等 substring 陷阱；
- must/preferred、否定句、条件句和“入职后学习”；
- 缺字段、OCR 错误、双栏、表格、页眉页脚和扫描件；
- 相同事实不同写法、相同关键词不同上下文；
- 数字存在但无基线/时间窗，或结果属于团队而非个人；
- 撤回 Evidence、来源冲突、过期 JD 和版本并发；
- 只改变姓名、学校、雇主品牌、格式或文本风格的反事实样本。

## 6. 在线验证

先执行 `docs/C6_PILOT_PROTOCOL.md` 中已预注册的 20 人探索性 crossover pilot，主要观察
首个有用输出时间、source-backed adoption、来源理解和安全事件。该 pilot 只能证明产品行为，
不能证明就业结果。

达到安全门禁后，再设计有统计功效的随机对照研究：固定任务、预注册主要终点、盲评改写质量、
报告效应量和置信区间。回电/面试/录用受市场、岗位、网络和雇主行为强烈影响，只有获得适当
同意、样本量和伦理/法律审查后才能作为长期探索指标，且不能训练成“录用概率”。

## 7. 对当前实现的差距审计

当前代码已经具备值得保留的基础：owner scope、Claim/Evidence、`unknown -> clarify`、改写前
确认、Fidelity 复核、不可变版本、幂等写入和未来行动不提高当前准备度。

优先修复项：

1. `job_profile.py` 只处理技能和经验年限，缺少 JD span、must/preferred、任务、资格和条件；
2. `matching_hybrid.py` 使用 substring 技能匹配和固定十维权重，尚无本地标注校准；
3. `potential_simulation.py` 的 40 字简介、必须有项目、量化影响阈值属于待验证启发式；
4. “缺少技能”目前仍由技能集合差得到，应先区分 `unknown`、partial 和真正冲突；
5. `create_rewrite_preview` 当前固定改 `summary` 并拼接来源文本，还不是字段级受约束编辑器；
6. potential score 假设补齐全部缺失技能，容易被误读成可实现收益；应改成候选人选择的单项情景；
7. 当前排序集只有 33 对且独立复核为 0/2，不能用现有高 nDCG 作为有效性证明；
8. 缺少 PDF/DOCX 导出的渲染—解析回环金标。

## 8. 实施顺序

1. **先建评测，不改权重**：扩展 schema 和标注协议，冻结 v1 gold set 与基线；
2. **改要求抽取**：保存 JD span、modality、type、confidence 和 taxonomy URI；
3. **改映射状态**：用 supported/partial/unknown/conflict 替代关键词命中/缺失二元值；
4. **改诊断路由**：删除未通过消融实验的普适阈值，加入 abstain；
5. **改局部生成**：字段级 source-constrained edit 和原子 provenance；
6. **加导出回环**：渲染、重解析、语义 diff 和视觉 QA；
7. **盲评与 pilot**：达到预注册门禁后再逐步放量；
8. **发布 Model Card/Datasheet**：每个 scorer/taxonomy/prompt 版本单独记录适用范围与失败模式。

第一轮代码优化应集中在第 1–3 步。没有金标前直接调固定权重，很可能只是把主观偏好写得
更复杂，无法让算法变得更可靠。

# AI Job Platform：数据、可信度推理、AI 面试与岗位推荐设计

> 版本：2026-07-24  
> 用途：供产品设计、数据治理和 Cursor 后续分批实现使用。  
> 本文不授权一次性改造代码；必须在现有安全整改完成后拆成独立 PR。

## 1. 产品结论

本产品不应宣称“判断简历真假”，应对外称为：

- 候选人侧：**履历证据体检 / Claim Passport**；
- 招聘方侧：**履历可信度审计 / 待澄清项**；
- 系统输出：**有证据支持、存在矛盾、证据不足、暂不可核验**。

原因：

1. 没有外部证据时，人类识别谎言的平均正确率约为 54%，接近随机判断；
2. 眼神、停顿、语速、紧张、语言风格都不是稳定的造假证据；
3. 矛盾可能来自记忆误差、简历压缩、口径不同或解析错误，不能直接等同于欺骗；
4. 更可靠的流程是把履历拆成原子 Claim，检索或向用户索取证据，再进行支持、矛盾或证据不足判断；
5. 招聘属于高影响场景，必须支持解释、人工复核、申诉和更正。

系统的核心不应是一个“真假分数”，而应是一个可追溯的图：

```text
候选人原始材料
    ↓
原子 Claim ──→ Evidence ──→ Claim 状态
    ↓             ↑
AI 面试追问 ──────┘
    ↓
结构化能力与偏好画像
    ├──→ 忠实简历补丁
    ├──→ 岗位推荐与解释
    └──→ 待提升项与下一步行动
```

## 2. 先接大模型 API，暂不训练基础大模型

### 2.1 推荐的混合架构

| 能力 | MVP 技术 | 是否允许模型最终决定 |
|---|---|---|
| 简历/JD 结构化解析 | 大模型 API + JSON Schema | 否，需规则校验 |
| Claim 原子化 | 大模型 API + 确定性切分 | 否，保存原文位置 |
| 面试问题自然语言生成 | 大模型 API | 否，问题目标来自规则/策略 |
| 面试回答摘要 | 大模型 API | 否，必须逐 Claim 引用原回答 |
| 技能标准化 | ESCO/O*NET 检索 + embedding | 可自动建议，用户可纠正 |
| 岗位初排 | 可解释规则/embedding 模型 | 否，必须显示硬约束和缺口 |
| Top-N 重排 | 大模型 API 或 cross-encoder | 否，不可覆盖硬约束 |
| 证据检索 | 关键词 + embedding/RAG | 否，只返回候选证据 |
| Claim 与证据关系 | 规则 + NLI + LLM verifier | 否，输出状态与理由 |
| 简历写回 | 模板/受约束生成 | 否，无证据不得写事实 |
| 招聘决策 | 人工 | 系统不得自动录用/淘汰 |

### 2.2 为什么现在不应自行训练大模型

- 公开简历—录用结果数据稀缺，且往往没有合法训练许可；
- 历史“录用”标签包含公司过去的偏好和歧视，不等于候选人真实能力；
- 当前产品更缺的是高质量标注协议、证据链和评测集，而不是更大的参数量；
- API + RAG 更容易更新岗位知识、保留证据来源和替换模型；
- 自训练基础模型成本高，但不能自动解决事实来源、校准、公平性和数据合法性。

### 2.3 何时值得训练自己的小模型

只有在取得明确授权的第一方数据并完成标注质检后，才考虑：

1. 技能/岗位 taxonomy linker；
2. resume–job 双塔召回模型；
3. reranker；
4. Claim 类型分类器；
5. Claim–Evidence NLI 校验器；
6. 面试问题选择策略。

这些模型也必须保留规则和人工复核层。不得使用未经单独同意的候选人简历、面试录音或对话做训练数据。

## 3. 可使用的数据及其用途

### 3.1 推荐的公开或授权数据

| 数据 | 主要用途 | 处理方式 | 重要限制 |
|---|---|---|---|
| ESCO 职业—技能分类 | 多语言技能标准化、职业邻接、岗位推荐 | 下载固定版本或调用 API | 保存版本与 URI |
| O*NET occupation/skills/tasks | 工作任务、技能、知识、工作活动画像 | 下载 CSV/JSON，映射到内部 taxonomy | 偏美国劳动力市场，不能直接代表中国公司 |
| 企业官方招聘页/JD | 目标岗位要求、技能和工作任务 | 优先取得授权或使用许可 API | 公开可见不等于允许批量抓取或训练 |
| 企业年报、官方技术博客、开源仓库 | 业务方向、技术环境、产品语境 | RAG 检索，保留 URL、时间和版本 | 只能形成公司语境，不能推断个人录用标准 |
| 政府职业、工资、就业趋势数据 | 职业路径与市场背景 | 聚合展示 | 不用于判断个人真实性 |
| 用户主动上传的证书、作品、项目文档 | Claim 支持证据 | 加密存储、最小化提取、可删除 | 必须取得明确目的授权 |
| 合作企业提供的结构化岗位与流程结果 | 匹配评测和校准 | 去标识化、目的限定、时间切分 | 历史结果不是“能力真值” |
| 用户主动确认的面试回答和简历修改 | 忠实改写、个人推荐 | 默认仅服务该用户 | 训练需要独立 opt-in |

### 3.2 不应直接收集或训练的数据

- 从社交平台、招聘网站批量抓取个人简历；
- 未取得授权的员工履历、面试录音、聊天记录；
- 人脸、眼动、声纹、口音、紧张程度和情绪推断；
- 性别、年龄、民族、籍贯、婚育、健康等敏感或保护属性作为推荐/淘汰特征；
- “是否录用”直接作为人才优劣标签；
- 来源和许可不清楚的 Kaggle 简历数据；
- 大公司员工公开主页拼成的所谓“录用画像”。

### 3.3 “大公司偏好画像”的正确做法

把“已录用员工画像”改成可追溯的四层：

1. **公开岗位需求画像**：来自公司官方 JD，描述明确要求；
2. **公司工作语境画像**：来自年报、技术博客、产品与开源项目，只描述业务和技术环境；
3. **证据偏好画像**：根据岗位任务说明更适合用项目、作品、代码、案例、证书还是结构化回答展示能力，不代表企业作出录用承诺；
4. **合作方校准画像**：只有企业明确授权的去标识化流程数据，可用于评估哪些信号与进入下一流程相关。

禁止输出“某学校、年龄、性别或现公司的人更容易被录用”。学校层级等历史相关性不得成为自动淘汰或 Potential action。

建议内部模型使用 `TargetRoleProfile`，而不是含义模糊的 `BigCompanyPreferenceProfile`：

```json
{
  "profile_id": "uuid",
  "company_id": "uuid",
  "role_family": "software_engineering",
  "job_level": "mid",
  "core_tasks": ["task-id"],
  "essential_skills": ["skill-uri"],
  "optional_skills": ["skill-uri"],
  "hard_constraints": ["constraint-id"],
  "work_context": ["high_availability", "cross_functional"],
  "accepted_evidence_types": ["work_sample", "project", "structured_answer"],
  "source_refs": ["official-jd-version", "official-blog-url"],
  "taxonomy_version": "esco-x/onet-y",
  "confidence": 0.78,
  "updated_at": "timestamp"
}
```

其中 `confidence` 反映来源完整性、时效和多源一致性，不由 LLM 自报；公开博客只能支持工作语境，不能自动转成必需录用条件。

### 3.4 数据获取方式：下载/API 优先，合规爬取兜底

ESCO 和 O*NET 不应优先使用网页爬虫：

- **ESCO**：核心 taxonomy 使用官方版本化 CSV/SKOS-RDF 下载；在线查询使用官方 Web Services API；保存 ESCO version、concept URI、下载时间和文件校验和；
- **O*NET**：高频和批量场景使用官方完整数据库下载，实时小范围查询使用注册后的 Web Services API；遵守 CC BY 4.0 署名和例外内容许可；
- **中国本地化**：增加《中华人民共和国职业分类大典（2022年版）》和公开的国家职业技能标准，建立与 ESCO/O*NET 的人工审核 crosswalk；
- **公司官方 JD、年报、技术博客**：优先官方 API、RSS、下载文件或合作方 feed；确需爬取时，逐站记录服务条款、robots、许可依据、抓取范围、频率和删除机制；
- **招聘平台数据**：没有书面许可或正式 API 时，不批量抓取；
- **个人数据**：即使页面公开，也不能自动视为可用于训练、画像或招聘决策。

建议建立 `DataSourceRegistry`：

```json
{
  "source_id": "onet-30.3",
  "source_type": "official_taxonomy",
  "acquisition": "bulk_download",
  "license": "CC-BY-4.0",
  "attribution": "O*NET 30.3 / U.S. Department of Labor",
  "version": "30.3",
  "retrieved_at": "2026-07-24T00:00:00Z",
  "checksum": "sha256:...",
  "allowed_uses": ["taxonomy", "matching", "research"],
  "contains_personal_data": false
}
```

采集服务与模型服务分离。原始来源进入版本化 source lake，经许可检查、解析、去重、质量检查和 taxonomy mapping 后才能进入搜索索引；任何模型输出都必须能回指 source/version。

对中国市场，ESCO/O*NET 只能作为语义骨架，不能直接作为“中国岗位真值”。必须用中国官方职业分类、经授权的中国 JD 和招聘专家评审校准翻译、职业边界、技能权重及级别。

## 4. 可信度审计：接近可靠人类推理的流程

### 4.1 Claim 状态

建议 MVP 使用以下状态，不使用 `true/false`：

- `supported`：当前证据明确支持；
- `contradicted`：可靠证据与 Claim 存在实质冲突；
- `insufficient_evidence`：目前证据不足；
- `unverifiable`：该类主张在当前条件下无法客观核验；
- `disputed`：候选人与证据来源存在争议，等待人工处理。

`clarified` 只表示“候选人已作说明”，不是“已证实为真”。

### 4.2 原子 Claim 模型

每条 Claim 只表达一个可以核验的事实，例如：

```json
{
  "claim_id": "stable-uuid",
  "subject": "候选人",
  "predicate": "负责",
  "object": "支付系统重构",
  "qualifiers": {
    "role": "核心开发",
    "time_range": "2024-03/2024-08",
    "metric": "P99 200ms → 120ms"
  },
  "source_span": {
    "resume_version_id": "version-uuid",
    "field_path": "work_experience[0].description",
    "text": "..."
  },
  "claim_type": "role_and_impact"
}
```

职位、时间、角色、动作、技术和结果指标必须拆开校验，防止一句话中一个真实片段掩盖多个无依据片段。

### 4.3 十步审计流程

1. **固定原始快照**：保存投递时 resume version，后续修改不覆盖历史；
2. **原子化**：把时间、职位、职责、技能、结果、证书拆成 Claim；
3. **可核验性分类**：区分身份/证书、任职、项目角色、结果指标、主观能力；
4. **一致性检查**：时间线重叠、职位年限、Claim 间矛盾、简历版本变化；
5. **证据检索**：只检索用户授权材料和合法公开来源，记录来源、时间、哈希及访问范围；
6. **自由叙述**：AI 面试先让用户完整说明，不把系统怀疑点提前塞进问题；
7. **目标追问**：围绕角色边界、具体行动、参与者、时间、可复核产物和指标口径追问；
8. **逐步呈现矛盾**：先取得独立回答，再展示已有矛盾让用户解释；不能诱导认错；
9. **多通道验证**：确定性规则 + evidence retrieval + NLI/LLM verifier；模型间不一致时升级人工；
10. **有限结论**：展示 Claim、证据、矛盾、用户解释和不确定性，不输出“此人造假”。

### 4.4 证据等级

证据强度不能只由 LLM 主观打分：

| 等级 | 示例 | 能支持什么 |
|---|---|---|
| A：权威或独立来源 | 可核验证书、经授权的任职证明、官方公开记录 | 对应的身份、证书或任职事实 |
| B：第一方业务材料 | 脱敏项目文档、代码提交、设计稿、绩效材料 | 参与和产出，但需核对归属 |
| C：关联证据 | 邮件、会议记录、同事证明、作品演示 | 增强可信度，通常不能单独定案 |
| D：候选人说明 | 面试回答、自述 | 形成澄清和后续问题，不等于外部验证 |

证据必须绑定到具体 Claim，不能用“一份证书”提高整份简历的总体真实性。

### 4.5 禁止使用的“测谎”信号

- 眼神回避；
- 面部表情；
- 心率、声纹、音调；
- 停顿和口头禅；
- 口音和语言流利度；
- 紧张或“不像自信的人”；
- 与其他候选人表达风格的相似程度。

这些信号容易歧视残障人士、非母语者和不同文化背景候选人，且不能稳定证明欺骗。

### 4.6 多学科认知依据

本系统追求的是**功能层面的专家推理相似性**，不是神经层面的“大脑仿真”。不应声称模型像人脑、具有意识或能读取真实意图。

| 学科 | 研究启示 | 对应产品控制 |
|---|---|---|
| 认知神经科学：来源监控 | 人会记得内容却混淆内容来自亲历、推断、他人转述还是想象 | Claim 保存 source span、回答来源、时间和主体；内容与来源分开评分 |
| 记忆心理学：重构性记忆 | 回忆会受后续信息、暗示和重复提问影响 | 先自由叙述，后目标追问；不强迫猜测；允许“记不清”；保留首轮回答 |
| 认知访谈 | 开放式回忆能获取更多信息，但新增细节仍需核验 | AI 先问开放题，再逐项补时间、角色、动作和结果 |
| 欺骗研究 | 人类和机器不能依赖简单行为或语言线索稳定识谎 | 禁止眼神、声音、表情和文风测谎；只处理证据与矛盾 |
| 认知偏误 | 确认偏误、锚定、可得性和过早闭合会污染判断 | 结论前强制生成替代解释；审计员先看 Claim 和证据，后看不相关背景 |
| 情报分析 ACH | 应让多个假设竞争，并寻找能证伪而非只支持首选解释的证据 | 同时评估真实、记忆误差、表述压缩、解析错误和证据不足等假设 |
| 临床推理 | 专家从数据获取、假设生成、检查和更新中形成判断，但也需要防偏流程 | 采用阶段化获取—假设—验证—更新，不允许单个启发式直接定案 |
| 贝叶斯决策 | 新证据应更新而不是替代既有不确定性；人并不擅长精确贝叶斯计算 | 记录 prior 来源、证据可靠性和更新轨迹；对外展示状态/区间，不展示伪精确“说谎概率” |
| 法证人因 | 上下文、期望、证据污染和缺少复核会制造系统性错误 | 无关敏感信息隔离、顺序揭示、双人复核、完整 chain of custody 和错误率评测 |
| 事实核验/NLI | 判断必须绑定可检索证据，长文本需要原子化 | Claim decomposition + retrieval + NLI/QA + 人工复核 |

### 4.7 与人类专家推理的功能对应

```text
人类专家                         系统
────────────────────────────────────────────────────
注意到一句可疑表述          →   Claim 原子化与风险分类
回忆“信息从哪里来”          →   source span / Evidence provenance
形成几个可能解释            →   competing hypotheses
寻找支持和反驳材料          →   双向 evidence retrieval
先开放询问、再针对追问      →   interview policy
根据新证据修正看法          →   versioned belief/state update
意识到自己可能不确定        →   calibrated insufficient/unverifiable
请第二个人复核              →   human review / disagreement queue
记录为什么得出结论          →   audit trail / Claim Passport
```

建议每个异常至少建立五个竞争假设：

- H1：Claim 获得证据支持；
- H2：Claim 与可靠证据实质冲突；
- H3：候选人记忆或时间口径误差；
- H4：简历压缩、解析或模型抽取错误；
- H5：目前没有足够信息。

系统首先比较“哪项证据最能区分这些假设”，再选择下一条问题。不得先假设造假，再寻找支持造假的线索。

### 4.8 认知相似度的评测，而不是宣传

不要用“像人类思考”作为无法验证的营销语。内部可以定义 `Cognitive Process Fidelity`：

1. **来源忠实度**：结论能否回到原始文本/证据；
2. **替代假设覆盖率**：是否考虑非欺骗解释；
3. **证据双向性**：是否同时检索支持和反驳信息；
4. **更新一致性**：相同新证据是否产生可复现的状态更新；
5. **不确定性校准**：证据不足时能否稳定拒绝定案；
6. **非暗示性**：问题是否避免植入答案；
7. **复核可读性**：人类审计员能否复现推理路径；
8. **偏差控制**：隐藏学校、性别、年龄等无关上下文后，结论是否保持稳定。

这个指标衡量的是流程是否接近规范化专家审计，而不是模型内部是否与大脑使用相同机制。

## 5. AI 面试：从聊天升级为结构化信息采集

### 5.1 三种面试模式必须分开

1. **证据澄清模式**：核对已有 Claim，不打能力分；
2. **能力模拟模式**：按目标岗位 competency rubric 提问和反馈；
3. **职业发现模式**：了解偏好、约束、动机和可接受的成长路径。

前端必须显示当前模式，避免用户把练习反馈误解为招聘结论。

### 5.2 问题生成策略

问题目标来自确定性策略，LLM 只负责自然表达：

1. 先问所有同岗位用户一致的结构化核心题；
2. 再根据回答选择信息增益最高的追问；
3. 优先补齐：
   - Claim 中缺失的角色边界；
   - 无来源的数字；
   - 与时间线冲突的信息；
   - JD 必需能力但简历没有证据的部分；
   - 用户的地点、薪资、行业、工作方式等硬约束；
4. 一个问题只解决一个主要不确定点；
5. 每个问题绑定 `claim_id`、`competency_id` 或 `preference_id`；
6. 达到证据充分、重复追问或用户拒答条件时停止。

结构化行为题可采用：

- Situation/Task：当时的情境和目标；
- Action：候选人本人具体做了什么；
- Result：结果和指标口径；
- Evidence/Reflection：可复核材料、复盘与限制。

### 5.3 面试回答的结构化产物

不要只保存 transcript 和一段 summary。每个回答应产生：

```json
{
  "answer_id": "uuid",
  "question_goal": "clarify_role",
  "claim_id": "uuid-or-null",
  "competency_id": "esco-or-onet-uri",
  "raw_answer_ref": "encrypted-object-ref",
  "observations": [
    {
      "type": "candidate_action",
      "text": "负责缓存策略和压测",
      "source_offsets": [18, 31],
      "confidence": 0.91
    }
  ],
  "candidate_confirmed": true,
  "allowed_uses": ["resume_assistance", "job_recommendation"],
  "share_with_employer": false
}
```

所有观察必须能定位回原回答，不得把 LLM 推断保存成用户事实。

## 6. 一次面试，驱动三种后续功能

### 6.1 生成或改写简历

只使用：

- 用户确认过的回答；
- `supported` Claim；
- 或明确标注为“候选人自述”的内容。

生成流程：

1. 从回答生成候选原子事实；
2. 用户逐条确认；
3. 与现有 Claim 合并或创建 revision；
4. 生成受约束 patch；
5. NLI/规则逐事实检查 patch 是否被证据蕴含；
6. 展示 diff、来源和用途；
7. 用户采纳后生成新 resume version，不覆盖投递快照。

没有数据时只能生成问题或写作框架，不能补职位、技术、数字和结果。

### 6.2 推荐合适岗位

把面试产物拆成四类信号：

- `demonstrated_skills`：有实例或证据；
- `self_reported_skills`：仅自述；
- `preferences`：行业、任务类型、团队、工作方式；
- `constraints`：地点、签证、薪资、时间、学历/证书硬要求。

推荐采用两阶段：

1. **召回**：标题、ESCO/O*NET 技能、embedding 和职业邻接召回；
2. **重排**：硬约束、已证明技能、偏好、成长距离和证据质量。

输出必须分开：

- 当前适合；
- 补充少量证据后可能适合；
- 需要中期学习；
- 存在不可忽略的硬门槛。

不得因为“证据不足”断言“不具备能力”；不得把没有证据的面试推断当作已掌握技能。

### 6.3 指导简历改写

对每个目标岗位生成三栏：

1. **已有但没写清楚**：面试中已出现可靠实例，可建议写入；
2. **可能具备但证据不足**：继续追问或要求材料；
3. **真实能力缺口**：推荐学习、项目或作品集行动，不伪装成已有经历。

每条建议显示：

- 对应 JD requirement；
- 来源 Claim/answer；
- 可否直接写回；
- 预计影响的模型维度；
- 下一步行动；
- “模型内匹配变化，不代表录用概率”。

#### 6.3.1 先区分问题类型

“增强竞争力”不能等同“补充数据”。系统先把问题分类为：

- `presentation_gap`：事实存在但表达不清；
- `relevance_gap`：经历没有映射到目标岗位；
- `evidence_gap`：主张缺少当前可观察证据；
- `differentiation_gap`：没有体现职责、方法、权衡或复杂度；
- `capability_gap`：真实能力尚未形成；
- `credibility_risk`：来源之间存在冲突；
- `career_narrative_gap`：经历与目标方向缺少连贯解释；
- `hard_constraint`：不能靠简历文字解决。

系统不得把“简历没写”推断成“候选人不会”，也不得把 `evidence_gap` 自动计为 `capability_gap`。

#### 6.3.2 多路径优化策略

对语义允许的问题生成 2–4 条可选路径：

| 策略 | 目标 | 写回条件 |
|---|---|---|
| `relevance_alignment` | 重排经历并映射到 JD 任务/技能 | 仅重组已有事实 |
| `role_clarity` | 区分个人、团队、协助和主导 | 必须有回答或 Claim 支持 |
| `method_and_tradeoff` | 展示问题、方案选择、权衡和限制 | 方法必须来自证据 |
| `scope_and_complexity` | 展示边界、上下游、风险或协作复杂度 | 不得虚构规模 |
| `outcome_expression` | 表达可验证的定性或定量结果 | 结果必须有来源 |
| `quantification` | 填写真实数字与口径 | 数字证据存在才可直接写回 |
| `evidence_strengthening` | 关联作品、代码、报告、证书 | 进入 Claim Passport |
| `career_narrative` | 说明能力迁移和职业方向 | 不新增经历 |
| `portfolio_or_work_sample` | 用作品或案例证明能力 | 生成未来行动，不冒充既有经历 |
| `skill_or_experience_building` | 学习、练习或完成项目 | 完成前不提升 current |
| `constraint_acknowledgement` | 确认硬门槛或寻找替代岗位 | 不生成润色 patch |

量化只是结果表达的子策略。没有数字时可以追问测量方法，也可以选择职责、方法、复杂度、岗位相关性、作品或定性结果；不能为了满足模板而要求每段经历都增加百分比。

#### 6.3.3 决策与排序

候选策略先经过确定性 eligibility gate，再排序：

```text
requirement importance
× gap severity
× actionability
× evidence confidence
− user cost
− hallucination risk
```

该式只表达排序因素，具体权重必须版本化、通过固定集校准并可解释。LLM 可以自然表达诊断和问题，但不能直接决定策略是否合法、最终分数或置信度。

每个 issue 保存：

- `issue_id`、`issue_type` 和目标 `requirement_id`；
- 输入 `claim_ids` / `answer_ids`；
- 2–4 个 `strategy_options`；
- `recommended_strategy_id` 与推荐理由；
- `requires_evidence`、`can_apply_now` 和 `next_action`；
- `expression_delta`、`evidence_delta`、`capability_delta`；
- source、taxonomy、rule、scoring、prompt/model 版本；
- 用户查看、切换、拒绝、采纳和完成事件。

用户选择策略后才构造反事实输入。表达、证据和能力三类变化分别重算；不得把文案改善展示成能力增长，也不得把单项 delta 直接相加。

#### 6.3.4 前端信息架构

建议页分为：

1. **现在可以优化**：有事实来源的重排和忠实改写；
2. **需要补充证据**：进入结构化追问、上传材料或 Claim Passport；
3. **需要真实提升**：学习、作品、模拟任务或经验计划；
4. **硬门槛**：明确限制、长期路径和替代岗位。

每个 issue 显示推荐策略和其他策略，用户可选择但不能绕过服务端 `can_apply_now`。按钮分别使用“预览改写 / 回答问题 / 添加证据 / 创建成长计划 / 查看替代岗位”，不可写回的占位模板不得显示“采纳到简历”。

## 7. 建议的数据模型

现有 Resume、Application、Claim thread 之上逐步增加：

### 7.1 核心实体

- `ResumeVersion`：不可变简历版本；
- `ApplicationResumeSnapshot`：投递快照；
- `Claim`：稳定 ID、类型、原文位置、当前 revision；
- `ClaimRevision`：Claim 文案与来源的版本历史；
- `EvidenceArtifact`：证据元数据、访问范围、保留期；
- `ClaimEvidenceLink`：支持/矛盾/相关及判定来源；
- `InterviewSession`：模式、目标岗位、同意范围；
- `InterviewQuestion`：rubric、目标 ID、问题版本；
- `InterviewAnswer`：原回答引用和用户确认；
- `CompetencyObservation`：能力观察及证据强度；
- `PreferenceProfile`：偏好和硬约束；
- `JobRequirement`：标准化技能、重要度、硬/软要求；
- `TargetRoleProfile`：岗位任务、技能、级别、工作语境、证据类型及来源版本；
- `OptimizationIssue`：岗位要求与候选人事实之间的缺口及分类；
- `OptimizationStrategyOption`：可选策略、资格门禁、成本、来源和模拟结果；
- `MatchExplanation`：匹配、缺口、证据和规则版本；
- `ResumePatchProposal`：patch、来源 Claim、忠实度结果。

### 7.2 必须记录的版本

- 模型供应商与 model ID；
- prompt/template version；
- taxonomy version；
- scoring/reranker version；
- evidence snapshot/hash；
- Claim extractor/verifier version；
- 用户确认、撤回和更正时间。

## 8. 隐私和目的隔离

面试开始前提供四个独立开关，不得捆绑：

1. 用回答帮助生成/改写简历；
2. 用回答进行个人岗位推荐；
3. 将指定回答或 Claim 分享给招聘方；
4. 去标识化后用于改进模型。

默认前三项按当前任务最小授权，第四项默认关闭。用户撤回后停止后续使用，并支持删除原始音频、文字稿、结构化观察和派生向量。

若把 AI 输出用于招聘方排序、淘汰或重大决定，必须增加：

- 明确告知；
- 人工复核；
- 解释与申诉；
- 数据更正；
- 偏差和分组表现评估；
- 自动化决策记录。

## 9. 评测协议

### 9.1 可信度审计

- Claim extraction precision/recall/F1；
- evidence retrieval Recall@K；
- Claim–Evidence 标签 Macro-F1；
- `contradicted` 的 precision 单独报告，优先降低误报；
- Brier score / ECE 校准；
- 不同 Claim 类型分别评估；
- 双人标注一致性和分歧裁决；
- 解析错误、同名公司、日期口径、团队成果归属等压力测试；
- 未见过的公司、岗位和时间段独立测试；
- 所有“造假”措辞测试应为零。

### 9.2 忠实简历生成

- 数字、时间、职位、角色和专有名词逐项 source coverage；
- unsupported atomic fact rate；
- patch 后语义是否被原文/面试回答蕴含；
- 用户拒绝率和人工错误分类；
- 未确认回答不得进入写回。

硬事实写回目标应接近 100% 可溯源，而不是只优化整体平均分。

### 9.3 AI 面试

- 问题与目标 competency/Claim 的相关性；
- 同岗位核心题一致性；
- 追问的信息增益和重复率；
- 回答结构化抽取准确率；
- 用户能否理解当前是练习、澄清还是职业发现；
- 不按口音、性别、年龄、表情和残障状态评分；
- 让招聘专家和候选人分别盲评。

### 9.4 岗位推荐

- Recall@K、nDCG@K；
- 硬约束违反率；
- 推荐理由忠实度；
- 冷启动表现；
- 行动完成后的反事实重算一致性；
- 分组曝光、推荐成本和可行动性差异；
- 线上点击/投递仅作为行为信号，不直接等同岗位适合度。

数据切分必须按候选人、公司和时间隔离，防止同一人的改写版本或同一 JD 模板泄漏到训练集和测试集。

### 9.5 多路径岗位适配建议

- issue type 的 Macro-F1，并单独报告 `evidence_gap` → `capability_gap` 误判率；
- strategy eligibility precision，尤其是无证据 `quantification` 的错误放行率；
- 适用问题中实质不同策略的覆盖率和平均数量；
- 量化建议占比、跨 issue 策略重复率和“只换标题”的伪多样性；
- 数字、角色、方法、范围、结果的 source coverage；
- 用户策略查看率、切换率、采纳率、拒绝原因和任务完成率；
- 候选人与招聘专家对相关性、可行动性、忠实度和冒犯性的盲评；
- 技术、产品、运营、设计、研究、管理和应届项目分层表现；
- `expression_delta`、`evidence_delta`、`capability_delta` 的重算一致性；
- 硬门槛被错误包装为简历改写的比例必须为 0。

## 10. 分阶段实施建议

### Phase A：数据治理和统一对象

1. 建立 source registry 和数据许可清单；
2. 接入固定版本 ESCO/O*NET；
3. 实现 ResumeVersion、Claim、Evidence 和 purpose consent；
4. 禁止原始面试回答直接覆盖 Resume；
5. 建立人工标注指南和 200–500 条金标准 Claim 集。

### Phase B：可信度审计 MVP

1. 原子 Claim 提取；
2. 时间线和内部一致性规则；
3. Evidence 上传、绑定和权限；
4. `supported/contradicted/insufficient/unverifiable/disputed`；
5. 证据追问；
6. 人工复核与申诉；
7. 禁止“真假/造假概率”。

### Phase C：结构化 AI 面试

1. 三种模式分离；
2. 岗位 rubric 与固定核心题；
3. Claim/competency/preference 目标化追问；
4. 回答 span 级溯源；
5. 用户逐条确认；
6. 同意范围与删除。

### Phase D：共享下游

1. 受约束简历 patch；
2. 面试证据增强的岗位推荐；
3. 基于 issue taxonomy 的“现在可优化/待补证据/真实提升/硬门槛”四类建议；
4. Claim Passport 展示；
5. 每个 issue 的多路径策略选择与资格门禁；
6. Potential action 用同一评分器重新模拟，并分开表达、证据和能力 delta。

### Phase E：自有模型与校准

只有在第一方授权数据达到质量门槛后：

1. 训练 taxonomy linker 和召回/rerank 小模型；
2. 训练领域 Claim–Evidence verifier；
3. 按公司和时间外推验证；
4. 做置信度校准和公平性审计；
5. shadow mode 运行，不立即影响招聘决定；
6. 通过人工复核后逐步放量。

## 11. 给 Cursor 的实施约束

```text
先阅读 AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md、CURSOR_EXECUTION_BACKLOG.md 和现有 Claim/interview/matching/resume 模块。
不要一次实现整份设计，也不要在当前安全整改 PR 中混入新功能。
先输出数据流、实体关系、现有模块复用点、数据库迁移、隐私目的、兼容风险和评测计划。
任何 LLM 输出都不能直接成为“造假”结论、录用/淘汰决定或无证据简历事实。
面试回答必须保留原文引用、用户确认和 allowed_uses，生成简历、岗位推荐、招聘方共享与模型训练分别授权。
每次只选择 Phase 中一个可独立验收的子任务，并等待用户确认。
```

## 12. 研究与标准依据

- Bond & DePaulo, 2006：无辅助情况下，人类谎言—真话判断平均约 54% 正确：[PubMed](https://pubmed.ncbi.nlm.nih.gov/16859438/)
- Hartwig & Bond, 2011：行为欺骗线索较弱，限制了识别准确性：[PubMed](https://pubmed.ncbi.nlm.nih.gov/21707129/)
- Vrij et al., 2022：没有简单可靠的语言欺骗线索；更可取的是自由叙述、独立信息与逐步呈现矛盾：[PubMed](https://pubmed.ncbi.nlm.nih.gov/35478762/)
- FEVER：Claim 应绑定 Evidence，并区分 Supported、Refuted、Not Enough Information：[ACL Anthology](https://aclanthology.org/W18-5501/)
- FActScore：将长文本拆成原子事实并逐项检查来源支持：[ACL Anthology](https://aclanthology.org/2023.emnlp-main.741/)
- TRUE：NLI 与 QA 方法对事实一致性检查具有互补价值：[ACL Anthology](https://aclanthology.org/2022.naacl-main.287/)
- RAG：显式检索有助于知识更新、事实性和来源追踪：[arXiv](https://arxiv.org/abs/2005.11401)
- OPM Structured Interviews：结构化面试具有工作内容相关性，并可在其他测评之外增加效度：[OPM](https://www.opm.gov/policy-data-oversight/assessment-and-selection/other-assessment-methods/structured-interviews/)
- OPM Job Analysis：从实际岗位任务识别所需 competencies，并可用于选拔、培训需求和职业发展；本产品据此从岗位要求生成优化与成长路径，而不是模仿历史录用者：[OPM](https://www.opm.gov/policy-data-oversight/assessment-and-selection/job-analysis/)
- O*NET：开放的职业、技能、任务和工作活动数据库：[O*NET Resource Center](https://www.onetcenter.org/database.html)
- ESCO：开放、多语言、稳定 URI 的职业—技能分类，可用于匹配、职业指导和研究：[European Commission](https://esco.ec.europa.eu/en/use-esco)
- Li et al., 2020：专家标注的 resume–job 匹配数据也只取得有限标注者一致性，说明标签需要明确指南和复核：[ACL Anthology](https://aclanthology.org/2020.emnlp-main.679/)
- ConFit：对比学习和困难负样本可改善 resume–job 排序，但仍依赖高质量配对数据：[arXiv](https://arxiv.org/abs/2401.16349)
- 《个人信息保护法》：对个人权益有重大影响的自动化决定，应支持说明和拒绝仅由自动化决策作出决定：[工业和信息化部](https://www.miit.gov.cn/jgsj/zfs/fl/art/2022/art_515a4b20c12f430eab54bb4f56d89f56.html)
- 《生成式人工智能服务管理暂行办法》：训练数据应来源合法，涉及个人信息需有同意或其他合法依据，并要求数据质量、准确性和非歧视：[国家网信办](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)
- EU AI Act：招聘和候选人选择系统属于高风险使用场景，强调数据治理、透明、记录、人工监督、准确性与稳健性：[EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689)
- Source Monitoring Framework：记忆内容与来源判断可分离，来源不完整时会发生重构和误归因：[Royal Society/PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC1692093/)
- Source memory neuroscience review：来源记忆涉及绑定、提取与评价过程，准确和错误记忆可来自相同的认知机制：[Psychological Bulletin/PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2859897/)
- False-memory review：误导性后续信息和带暗示的问题可能改变回忆及其来源归属：[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10567586/)
- Forced confabulation meta-analysis：强迫回答不知道的问题可能形成后续虚假记忆，系统必须允许“不知道/记不清”：[PubMed](https://pubmed.ncbi.nlm.nih.gov/37083745/)
- Cognitive Interview field study：基于记忆提取原则的访谈获得更多信息，但这些信息仍需独立核验：[PubMed](https://pubmed.ncbi.nlm.nih.gov/2793772/)
- Judging Truth review：人会受默认相信、加工流畅性和记忆一致性影响，不能把“听起来顺”当成真实：[Annual Review of Psychology](https://www.annualreviews.org/content/journals/10.1146/annurev-psych-010419-050807)
- Analysis of Competing Hypotheses：显式比较替代解释并关注证伪证据，可减少只支持首选假设的倾向：[CIA Tradecraft Primer](https://www.cia.gov/resources/csi/static/955180a45afe3f5013772c313b16face/Tradecraft-Primer-apr09.pdf)
- NIST Human Factors：证据解释会受到认知、确认和上下文偏误影响，需要验证、复核和不确定性表达：[NIST](https://www.nist.gov/forensic-science/human-factors-forensic-science)
- O*NET 获取与许可：数据库可版本化下载，多数内容采用 CC BY 4.0，需署名并检查例外内容：[O*NET](https://www.onetcenter.org/database.html)
- ESCO 数据获取：官方提供版本化 CSV/SKOS-RDF 下载、Web API 和 Local API，不必依赖网页爬虫：[ESCO](https://esco.ec.europa.eu/en/use-esco/use-esco-services-api)
- 《中华人民共和国职业分类大典（2022年版）》：中国职业 taxonomy 本地化的官方基础：[人力资源和社会保障部门](https://rsj.shannan.gov.cn/zwgk/zcfg/rsrc/202304/t20230421_118929.html)

# AI Job Platform 第二轮产品化改造：Cursor 完整实施规格

> 文档版本：2026-07-28  
> 适用仓库：`ai-job-platform`  
> 实施范围：PR10–PR17  
> 文档用途：作为 Cursor 逐 PR 编码、迁移、测试和验收的权威实施输入  
> 产品阶段：在市场验证、收费和资金流之前，完成可邀请真实用户试用的合规成品

---

## 0. 给 Cursor 的最高优先级指令

在修改任何代码前，完整阅读：

1. 本文件 `CURSOR_SECOND_ROUND_PRODUCT_IMPLEMENTATION_SPEC.md`；
2. `CURSOR_DEFINITION_OF_DONE.md`；
3. `CURSOR_EXECUTION_BACKLOG.md`；
4. `AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`；
5. `PR8_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`；
6. `PR9_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`；
7. 当前 `git status`；
8. 当前批次涉及的模型、路由、服务、迁移和测试。

执行约束：

1. **不得一次实现 PR10–PR17。** 每次只执行一个明确指定的 PR；未指定时只做只读差距审计，不编码。
2. 工作区现有已暂存、未暂存和未跟踪内容全部视为用户资产。禁止 `reset`、`checkout`、覆盖或顺手格式化无关文件。
3. 不得重新平行实现已有的 Resume、ResumeClaim、ClaimEvidence、ClaimRevision、ClaimEvent、JobApplication、InterviewResult、ResumeSuggestion、PotentialSimulationEvent 等能力。
4. 新模型必须通过迁移、兼容读写和数据回填逐步接入，不能一次性破坏旧接口。
5. 所有授权在后端进行。不得信任前端传入的 `user_id`、角色、资源归属、Claim 状态、`can_apply_now`、评分或判断结果。
6. 所有 AI 结果默认是建议或待确认结构，不是用户事实、第三方验证事实、录用结论或淘汰结论。
7. 无证据时只能追问、标记缺口、生成未来行动或提供空白写作框架；不得补入职位、职责、技术、数字、客户、规模、结果或因果关系。
8. 不显示或存储模型原始隐藏思维链。产品只显示结构化、可审计的“决策路径”。
9. 不实现“测谎”“造假概率”“可信度分数”或基于表情、声纹、口音、停顿、紧张程度的判断。
10. 招聘方最终录用、淘汰和争议处理必须由人完成。LLM 不能自动淘汰候选人。
11. 每个 PR 必须先给出需求追踪矩阵和风险，再补失败测试，再实现，再执行完整门禁。
12. 任一验收条件缺少证据时只能报告“部分完成”，不能因构建通过或少量测试通过宣称完成。

### 0.1 文档冲突时的优先级

本轮产品目标和 PR10–PR17 的行为以本文件为准。若旧文档仍使用以下术语，以本文件替换：

| 旧术语 | 第二轮权威术语 |
|---|---|
| 可信度分数、真假分数 | 删除；改为证据状态、待澄清项和人工复核状态 |
| Potential Score | 岗位准备度与行动路径 |
| Potential Simulation | 可提升空间模拟；作为岗位准备度的一部分保留 |
| 大公司录用偏好画像 | 企业岗位要求、职业通用画像、公司公开语境、市场信号四层分离 |
| 测谎、识别造假 | 一致性与证据充分性检查 |
| 模型思考过程 | 结构化决策路径 |

若安全、权限、数据不可变性要求与旧实现冲突，采用更严格的要求。

---

## 1. 第二轮的产品目标

本轮不是增加若干孤立 AI 功能，而是把 PR9 已有能力收敛为一个完整产品：

> 以 Evidence Vault 为候选人的长期职业记忆网络，以 Claim Passport 记录完整求职履历，以目标岗位为入口，驱动岗位诊断、忠实改写、结构化面试、岗位准备度行动路径和招聘方证据筛选。

### 1.1 候选人价值

候选人能够：

1. 长期积累职业经历、原子 Claim、Evidence、作品、结果和修订历史；
2. 以地图和时间线理解自己的职业记忆；
3. 先选择目标岗位，再获得全面诊断；
4. 从 Vault 已有事实中生成岗位定制简历；
5. 对证据不足处使用 AI 面试官追问和澄清；
6. 清楚看到每条改写的来源和变更依据；
7. 区分“表达没写好”“证据没补全”“真实能力缺失”“硬门槛”；
8. 获得岗位准备度和下一步行动，而不是虚假的录用概率；
9. 关闭 AI 后继续使用手动编辑、规则诊断、检索和投递功能；
10. 控制哪些数据仅自己可见、用于求职辅助、分享给招聘方或用于模型改进。

### 1.2 招聘方价值

招聘方能够：

1. 配置岗位相关且合法的硬性条件；
2. 批量执行硬条件筛选；
3. 选择关键词和标准化技能进行二次筛选；
4. 使用 LLM 总结候选人对岗位要求提供的证据；
5. 发现信息缺口、内部不一致和需要澄清的地方；
6. 查看可追溯的判断依据和可能的合理解释；
7. 向具体 Claim 发起澄清；
8. 在人工复核后作出决定；
9. 不接触候选人未授权的 Vault 内容；
10. 不使用敏感属性、代理属性或未经验证的“公司偏好画像”筛选。

### 1.3 本轮不做

以下项目留到下一阶段：

- 收费、支付、分账和资金流设计；
- 大规模市场投放和增长实验；
- 用未经验证的录用结果训练排序模型；
- 全自动招聘决策；
- 基础大模型训练；
- 视频微表情、情绪、声纹或口音分析；
- 自动背调或未经用户授权的外部个人信息抓取；
- “保证拿到 Offer”“保证简历真实”等承诺。

### 1.4 用户需求追踪矩阵

| 用户确认的产品要求 | 权威落地章节 | 主要实施 PR |
|---|---|---|
| Claim Passport 覆盖整个求职过程 | 4.1、5.1–5.6、7.2 | PR11、PR13 |
| Evidence Follow-up 合入 AI 面试官 | 5.9、6.5、PR12 | PR12 |
| 从 Vault 提取经历并提示“看到你有……可以这样写……” | 6.4、7.5、PR13 | PR13 |
| Fidelity Proof 和全部改写依据 | INV-01/02/10、5.11、6.4 | PR10、PR13 |
| 冲突检测而非测谎 | INV-06、10、PR15 | PR15 |
| 模拟资深 HR 工作流程 | 10、PR15 | PR15、PR17 |
| 保留 Claim 追问和澄清聊天 | 6.1、7.2、PR12 | PR11、PR12 |
| JD、画像和 AI 顾问提高竞争力 | 6.3、7.4、9.2、PR14 | PR14 |
| 删除可信度分数 | 0.1、5.13、PR15 | PR13、PR15 |
| Potential 改为岗位准备度与行动路径 | 0.1、5.10、PR13 | PR13 |
| 全面指出多个简历问题 | 6.4、7.5、PR13 | PR13 |
| 优化 expression/evidence/capability 分层 | 5.10、6.4、PR13 | PR13 |
| 先选择岗位再检索和改写 | 4.1、6.4、PR13 | PR13 |
| Evidence Vault 以记忆 Map 呈现 | 4.3、7.3、PR11 | PR11 |
| 显示依据和结构化决策路径 | 5.12、6.4、10.3 | PR13、PR15 |
| 用户可以关闭 AI | INV-07、7.6、PR16 | PR10、PR16 |
| 招聘方硬条件 → 关键词 → LLM 批筛 | 4.2、5.13、6.6、PR15 | PR15 |
| 明确 AI API 和可替换架构 | 8 | PR10 |
| 画像数据真实、合法、有效 | 5.7、9 | PR10、PR14 |
| 改写和面试数据来源及训练方法 | 9.4–9.6 | PR14、PR17 |

---

## 2. 不可破坏的产品不变量

以下规则必须通过服务端测试固定：

### INV-01：事实来源

写入简历的每个原子事实必须至少满足一个条件：

- 来自当前简历原文；
- 来自用户已确认的 Claim；
- 来自用户已确认、允许用于简历辅助的 Interview Observation；
- 来自用户提交并绑定的 Evidence；
- 来自第三方已验证材料，且授权范围允许。

目标 JD、职业词库、公司资料、LLM 常识和招聘方期待都不能成为候选人过去经历的事实来源。

### INV-02：事实新增门禁

出现以下任何变化时，不能直接应用：

- 新实体；
- 新职位或职级；
- 新技术或技能；
- 新职责；
- 新数字、比例、金额或规模；
- 新客户或行业；
- 新结果；
- 新因果关系；
- 团队成果变成个人成果；
- “参与”扩大为“负责、主导、管理、决策”；
- 时间范围扩大。

系统必须返回 `needs_confirmation` 或 `needs_evidence`，并进入 AI 面试或人工补充流程。

### INV-03：状态不等于真实性

- `user_confirmed` 只表示用户确认；
- `supported_by_user_evidence` 只表示存在用户提供的支持材料；
- `employer_reviewed` 只表示招聘方已阅读或追问；
- 只有授权第三方核验完成后才可显示 `third_party_verified`；
- `clarified`、`answered`、`reviewed` 均不代表事实已证明。

### INV-04：历史不可变

投递时的 Resume、Claim、Evidence 摘要、授权范围和岗位要求必须保存不可变快照。后续修改不能污染历史申请。

### INV-05：证据不足不等于能力不足

`evidence_gap` 不能自动转为 `capability_gap`。只有用户确认没有相关能力或明确完成能力评估后，才能进入真实能力缺口。

### INV-06：冲突不等于欺骗

冲突输出必须包括：

- 冲突的两个或多个来源；
- 冲突类型；
- 可能的合理解释；
- 建议追问；
- 人工复核状态。

禁止输出“撒谎、造假、欺诈概率、可信度百分比”。

### INV-07：AI 可关闭

用户关闭 AI 后：

- 不调用模型；
- 不发送新数据给模型供应商；
- Evidence Vault、人工编辑、规则校验、关键词搜索和投递仍可用；
- 已生成内容清楚标注来源；
- 用户可以删除允许删除的 AI 派生数据。

### INV-08：招聘决定由人负责

LLM 输出不能直接改变为 `rejected`、`hired` 等终态。硬性条件规则也只能生成筛选结果；最终状态变更必须有被授权招聘人员的明确操作和审计事件。

### INV-09：画像来源分层

企业具体岗位要求只能来自企业 JD 或企业授权输入。职业标准、公司公开资料和市场统计不得伪装成企业录用偏好。

### INV-10：可追溯

所有重要 AI 输出必须记录：

- 输入对象 ID 与快照哈希；
- 数据来源 ID；
- rule/scoring/taxonomy/prompt/model 版本；
- 输出 Schema 版本；
- 门禁结果；
- 用户确认或人工复核事件。

---

## 3. 当前实现基线与复用策略

### 3.1 必须复用

| 当前对象/模块 | 第二轮用途 |
|---|---|
| `Resume` | 当前可编辑简历容器；逐步增加不可变 ResumeVersion |
| `ResumeClaim` | Claim Passport 稳定 Claim；增加用户和职业经历维度 |
| `ClaimEvidence` | 现有轻量证据记录；迁移为 EvidenceArtifact 关系的兼容层 |
| `ClaimRevision` | Claim 改写和 Fidelity 历史 |
| `ClaimApplicationLink` | 投递 Claim 快照 |
| `ClaimEvent` | Claim 追加式审计事件 |
| `PotentialSimulationEvent` | 可提升空间模拟事件；后续连接岗位准备度 |
| `ResumeSuggestion` | 兼容旧诊断建议；不得再建立第三套建议表 |
| `JobDescription` | 企业 JD 原文与解析结果 |
| `JobApplication` | 求职过程中的正式投递对象 |
| `InterviewResult` | 旧面试结果兼容入口；迁移到结构化 session/question/answer |
| `matching_hybrid.py` | 反事实重算和解释的现有评分器 |
| `job_profile.py` | 企业 JD 为事实、taxonomy 只标准化的边界 |
| `fidelity_proof.py` | 忠实度检查底层能力 |
| `claim_reasoning.py` | Claim 一致性和证据关系的现有逻辑 |

### 3.2 当前必须修复的问题

1. `llm_client.py`、`interview.py`、`resume_variants.py` 默认使用已下线的 `deepseek-chat`。
2. `resume_variants.py` 的规则 fallback 会自动补入岗位技能及通用成果，违反 INV-01/02。
3. `matching_hybrid.py` 存在把缺失岗位技能补为 `intermediate` 的模拟逻辑；未来技能必须为 `planned`，不能进入当前能力。
4. `statistical_benchmark.py` 使用 Reddit、V2EX、Hacker News 等来源，不能形成企业录用画像。
5. `CredibilityAuditRecord.risk_score` 和相关 UI 仍可能传递“可信度分数”概念，需要兼容迁移和隐藏。
6. `ResumeClaim` 当前强绑定某份 Resume，尚不能自然覆盖候选人的完整职业周期。
7. `ClaimEvidence` 当前主要保存文本摘要，缺少统一 artifact、授权、保留期、来源版本和访问范围。
8. `InterviewResult` 当前模式和产物不足以表达结构化访谈、问题目标、回答 span 和用途授权。
9. PR9 的建议主要是运行时 snapshot，尚缺可持久化的诊断 issue、策略、用户选择和行动计划模型。

### 3.3 禁止的实现捷径

- 不得用一个新的 JSON 大字段代替所有关系和审计；
- 不得把 Evidence Vault 实现成“上传文件列表 + 一张前端关系图”；
- 不得将 LLM 返回的 ID、权限或 `can_apply_now` 原样信任；
- 不得用 prompt 声明“不要虚构”替代服务端 Fidelity 门禁；
- 不得用关键词命中直接判定能力已具备；
- 不得用论坛样本或历史录用者统计生成企业筛选权重；
- 不得在未完成数据登记时自动爬取网站；
- 不得将模型调用失败降级为虚构内容；
- 不得把未来学习计划写进当前简历；
- 不得暴露内部模型原始思维链。

---

## 4. 目标信息架构

### 4.1 候选人主流程

```text
导入/创建目标岗位
    ↓
生成带来源的岗位要求矩阵
    ↓
检索 Evidence Vault 中相关经历、Claim 和 Evidence
    ↓
全面诊断：Expression / Evidence / Capability + 辅助类型
    ↓
现在可优化 ───────→ 忠实改写预览
需要补证据 ───────→ AI 面试官 / 上传 Evidence / Claim 聊天
需要真实提升 ─────→ 岗位准备度行动计划
硬性门槛 ─────────→ 长期路径或替代岗位
    ↓
逐条确认并生成 ResumeVersion
    ↓
投递并写入 Claim Passport 历史
```

### 4.2 招聘方主流程

```text
企业提交并确认 JD
    ↓
配置合法、岗位相关的硬性条件
    ↓
批量候选人进入 Screening Run
    ↓
确定性硬条件筛选
    ↓
招聘方选择的关键词 + taxonomy 归一化
    ↓
LLM 汇总证据 / 信息缺口 / 一致性问题 / 替代解释
    ↓
人工复核
    ├── 发起 Claim 澄清
    ├── 继续流程
    └── 人工作出最终决定
```

### 4.3 Evidence Vault 地图

至少提供四种视图：

1. **时间线视图**：经历、项目、教育、面试、简历版本、投递和修订；
2. **能力视图**：Skill/Competency → Claim → Evidence；
3. **证据网络视图**：Claim 与 Evidence 的支持、冲突、相关关系；
4. **目标岗位视图**：Requirement → 已有证据 → 待澄清 → 能力行动。

地图必须由服务端授权后的节点和边生成。前端不能通过获取整个 Vault 后自行隐藏招聘方无权内容。

---

## 5. 领域模型与数据库设计

所有时间使用带时区 UTC；ID 沿用 UUID 字符串；PostgreSQL 为生产权威数据库；JSON 仅用于版本化快照或不稳定扩展字段，核心关系必须结构化。

### 5.1 `career_experiences`

候选人的长期经历，不隶属于某一份简历。

| 字段 | 要求 |
|---|---|
| `id` | UUID PK |
| `user_id` | FK users，非空，索引 |
| `experience_type` | work/project/education/volunteer/freelance/award/other |
| `organization` | 可空 |
| `title` | 可空 |
| `start_date` / `end_date` | 可空；允许用户只提供月份或年份时保存 precision |
| `date_precision` | day/month/year/unknown |
| `description` | 用户原始描述 |
| `source_kind` | resume_import/interview/manual/evidence_import |
| `source_ref` | 原始对象引用 |
| `workflow_state` | active/archived/withdrawn |
| `created_at` / `updated_at` | 审计时间 |

权限：只有 owner 可写；招聘方只能通过 Application Snapshot 读取被分享部分。

### 5.2 扩展 `resume_claims`

不新建平行 Claim 表。分阶段增加：

- `user_id`：从 Resume owner 回填，最终非空；
- `career_experience_id`：可空 FK；
- `origin_kind`：resume/interview/manual/evidence/import；
- `source_object_type`、`source_object_id`；
- `source_span`：原文 offset 或结构化 field path；
- `confirmation_state`：unconfirmed/user_confirmed/withdrawn；
- `confirmed_at`；
- `sensitivity_level`：normal/personal/sensitive；
- `default_visibility`：private/application_selected；
- `superseded_by_claim_id`：Claim 合并/拆分历史。

兼容策略：

1. 先增加可空字段；
2. 根据 Resume.user_id 回填；
3. 为无法回填的孤儿数据生成审计报告，不静默删除；
4. 新写入同时维护旧 `resume_id` 和新归属；
5. API 完成切换后再评估是否允许 `resume_id` 为空；
6. 稳定 Claim ID 绝不因迁移重新生成。

### 5.3 `evidence_artifacts`

保存 Evidence 元数据，原件存储在安全对象存储，不直接进数据库。

| 字段 | 要求 |
|---|---|
| `id` | UUID PK |
| `owner_user_id` | FK users |
| `artifact_type` | document/link/code/sample/certificate/image/user_statement/other |
| `title` | 用户可理解标题 |
| `object_ref` | 加密对象引用；文本证据可为空 |
| `source_url` | 可空，不保存带临时 token URL |
| `content_hash` | SHA-256 |
| `mime_type` / `size_bytes` | 文件元数据 |
| `extracted_text_ref` | 加密文本对象引用 |
| `issuer` | 第三方签发者，可空 |
| `occurred_at` | 证据发生时间，可空 |
| `verification_status` | user_provided/third_party_verified/rejected/withdrawn |
| `verification_ref` | 验证记录引用 |
| `allowed_uses` | 结构化用途集合 |
| `default_visibility` | private/application_selected |
| `retention_until` | 保留期限 |
| `withdrawn_at` / `deleted_at` | 生命周期 |
| `created_at` / `updated_at` | 审计时间 |

MVP 不要求保存身份证、工资单等高敏感原件。若用户尝试上传，应明确阻止或经过单独的高敏流程。

### 5.4 扩展 `claim_evidence`

保留表和旧 ID，增加：

- `artifact_id`；
- `relationship`：supports/contradicts/related；
- `source_span`；
- `link_created_by`；
- `link_method`：manual/rule/model/third_party；
- `model_suggestion_id`；
- `candidate_confirmed`；
- `access_scope`；
- `valid_from` / `valid_until`。

旧的文本 `summary/source` 继续兼容读取。新 Evidence 优先创建 Artifact 后再建 link。

### 5.5 `resume_versions`

每次用户正式采纳改写或投递前创建不可变版本。

字段：

- `id`、`resume_id`、`user_id`；
- `version_number`；
- `parsed_json_snapshot`；
- `raw_text_snapshot`；
- `content_hash`；
- `created_reason`：manual_edit/rewrite/application/import；
- `parent_version_id`；
- `created_by`；
- `created_at`。

唯一约束：`(resume_id, version_number)`。

### 5.6 `resume_version_claim_links`

记录某个简历版本中使用了哪些 Claim：

- `resume_version_id`；
- `claim_id`；
- `claim_revision_id`；
- `field_path`；
- `text_snapshot`；
- `evidence_ids_snapshot`；
- `fidelity_result_snapshot`；
- `created_at`。

### 5.7 `data_sources` 与 `data_source_versions`

所有画像、taxonomy、评测和外部数据进入系统前必须登记。

`data_sources`：

- owner/organization；
- acquisition_method；
- license_name/license_url/contract_ref；
- allowed_product_uses；
- training_allowed；
- contains_personal_data；
- processing_region；
- attribution_text；
- deletion_contact；
- status：pending_review/approved/restricted/revoked。

`data_source_versions`：

- source_id；
- external_version；
- retrieved_at；
- effective_at；
- checksum；
- raw_object_ref；
- parser_version；
- expires_at；
- validation_report；
- superseded_by_version_id。

服务端必须拒绝将 `pending_review/revoked` 来源用于生产画像或训练集。

### 5.8 `target_role_profile_snapshots` 与 `job_requirements`

`target_role_profile_snapshots`：

- `job_id`；
- 企业 JD 原文/解析快照哈希；
- profile schema version；
- parser/rule/model/taxonomy versions；
- status：draft/employer_confirmed/superseded；
- created_at。

`job_requirements`：

- profile_snapshot_id；
- requirement_type：task/skill/experience/education/certificate/location/salary/work_mode/other；
- raw_text；
- canonical_id/canonical_label；
- importance；
- requirement_level：required/preferred/context；
- is_hard_constraint；
- employer_confirmed；
- source_offset；
- source_id/source_version_id。

只有企业输入或企业确认的 requirement 能被标记为该企业岗位要求。

### 5.9 结构化面试模型

新增：

#### `interview_sessions`

- `user_id`；
- `mode`：vault_builder/target_gap/claim_clarification/practice；
- `job_id`、`resume_id`，可空；
- `status`：active/completed/revoked；
- 四类用途同意快照；
- interviewer policy/rubric/prompt/model version；
- created/completed/revoked 时间。

#### `interview_questions`

- `session_id`；
- `sequence_no`；
- `question_goal`；
- `claim_id` / `requirement_id` / `competency_id`；
- `core_or_probe`；
- `question_text`；
- `policy_version`；
- `generated_by`；
- `created_at`。

#### `interview_answers`

- `question_id`；
- `raw_answer_ref`；
- `answer_text_snapshot`；
- `user_declined`；
- `confirmed_at`；
- `allowed_uses`；
- `share_with_employer`；
- `created_at`。

#### `interview_observations`

- `answer_id`；
- `observation_type`：situation/task/candidate_action/team_action/method/result/metric/evidence/reflection/preference/constraint；
- `text`；
- `source_start/source_end`；
- `claim_id`；
- `candidate_confirmation_state`；
- `extractor_version`；
- `created_at`。

LLM 推断不能以 `candidate_confirmed` 状态保存。

### 5.10 诊断、策略与行动模型

复用 PR9 枚举和事件，新增可查询实体：

#### `optimization_issues`

- `resume_version_id`；
- `profile_snapshot_id`；
- `issue_type`；
- `target_requirement_id`；
- `diagnosis`；
- `severity`：blocker/high/medium/low；
- `source_refs`；
- `status`：open/resolved/dismissed/superseded；
- rule/model versions。

#### `optimization_issue_claim_links`

- issue_id；
- claim_id；
- relation：supports/gap/conflict/related。

#### `optimization_strategy_options`

- issue_id；
- PR9 strategy 枚举；
- `requires_evidence`；
- 服务端权威 `can_apply_now`；
- `next_action`；
- `affected_dimensions`；
- `time_horizon`；
- `user_cost`；
- `hallucination_risk`；
- `recommended`；
- `eligibility_reason`；
- `counterfactual_snapshot`；
- 三层 delta；
- rule/scoring versions。

#### `readiness_actions`

- user_id/job_id/issue_id/strategy_id；
- action_type；
- title/description；
- status：planned/in_progress/completed/abandoned；
- completion_evidence_id；
- expected_time_horizon；
- user_cost；
- created/completed 时间。

完成未来行动不自动将技能变成“已具备”。必须产生 Claim/Evidence 并经用户确认后重新计算当前准备度。

### 5.11 `resume_patch_proposals`

- resume_version_id；
- target_job_id；
- issue_id/strategy_id；
- field_path；
- before_text/after_text；
- atomic_changes；
- source_claim_ids/source_evidence_ids/source_answer_ids；
- fidelity_result；
- status：draft/needs_confirmation/ready/applied/rejected/expired；
- prompt/model/rule versions；
- created/applied 时间。

后端 apply 时重新加载 proposal 和所有来源，重新执行 Fidelity，不信任客户端提交的 `after_text` 或 `can_apply_now`。

### 5.12 AI 审计模型

#### `ai_invocations`

只保存必要元数据：

- task_type；
- provider/model alias 和实际 model ID；
- prompt/schema version；
- input snapshot hashes，不默认保存完整 PII；
- data_region；
- token/cost/latency；
- status/error category；
- user/org；
- created_at。

#### `decision_traces`

保存可向用户展示的结构化依据：

- decision_type；
- subject_type/subject_id；
- observed_source_refs；
- rules_fired；
- findings；
- alternative_explanations；
- uncertainties；
- recommended_next_actions；
- human_review_required；
- created_at。

禁止保存或展示原始 chain-of-thought。

### 5.13 招聘方批筛模型

#### `screening_runs`

- job_id/employer_id；
- profile_snapshot_id；
- status；
- candidate_count；
- rules_version/keyword_version/model_version；
- created_by/created/completed 时间。

#### `screening_rules`

- run_id；
- rule_type：hard_constraint/keyword/taxonomy；
- field/operator/value；
- employer_confirmed；
- legal_basis_note；
- order_no；
- enabled。

#### `screening_results`

- run_id/application_id；
- hard_filter_status：pass/fail/unknown；
- hard_filter_reasons；
- keyword_hits；
- evidence_summary；
- gap_findings；
- consistency_findings；
- alternative_explanations；
- status：pending_review/reviewed/clarification_requested；
- reviewer_id/reviewed_at。

禁止字段：credibility_score、lie_probability、automatic_rejection_reason。

---

## 6. API 契约

所有列表接口分页；所有写接口支持幂等键；对象级权限失败使用统一防枚举响应；所有错误使用现有统一错误结构。

### 6.1 Candidate Career Passport

```text
GET    /career-passport/overview
GET    /career-passport/timeline
GET    /career-passport/map?view=timeline|capability|evidence|job&job_id=
POST   /career-passport/experiences
PATCH  /career-passport/experiences/{experience_id}
POST   /career-passport/experiences/{experience_id}/claims
PATCH  /career-passport/claims/{claim_id}
POST   /career-passport/claims/{claim_id}/confirm
POST   /career-passport/claims/{claim_id}/withdraw
GET    /career-passport/claims/{claim_id}/history
POST   /career-passport/claims/{claim_id}/chat/messages
GET    /career-passport/claims/{claim_id}/chat/messages
```

Claim 聊天只负责追问、澄清、补证和修订。每条 AI 消息必须带 `question_goal` 和关联 Claim；不能在聊天中绕过正式确认或改写 apply。

保留旧 `/resumes/{resume_id}/claims/*` 路由，在过渡期内部调用同一 service。

### 6.2 Evidence Vault

```text
POST   /evidence-vault/artifacts/init-upload
POST   /evidence-vault/artifacts/{artifact_id}/complete-upload
GET    /evidence-vault/artifacts
GET    /evidence-vault/artifacts/{artifact_id}
PATCH  /evidence-vault/artifacts/{artifact_id}
DELETE /evidence-vault/artifacts/{artifact_id}
POST   /evidence-vault/claims/{claim_id}/links
DELETE /evidence-vault/claims/{claim_id}/links/{link_id}
PATCH  /evidence-vault/artifacts/{artifact_id}/permissions
```

上传使用 allowlist MIME、内容嗅探、大小限制、病毒扫描、随机对象名和私有 bucket。下载必须使用短期签名 URL。

### 6.3 Target Job 与 AI 顾问

```text
POST   /advisor/target-jobs/import
GET    /advisor/jobs/{job_id}/profile
POST   /advisor/jobs/{job_id}/profile/confirm
GET    /advisor/jobs/{job_id}/source-trace
POST   /advisor/jobs/{job_id}/diagnostics
GET    /advisor/jobs/{job_id}/diagnostics/{diagnostic_id}
GET    /advisor/jobs/{job_id}/readiness
POST   /advisor/jobs/{job_id}/actions/{action_id}/status
POST   /advisor/jobs/{job_id}/chat/messages
```

Advisor 回答的每一条事实性结论必须返回：

- `statement_type`：employer_requirement/occupation_reference/company_context/market_signal/candidate_evidence/inference；
- source ID、版本、时间；
- 适用范围；
- 置信说明；
- 是否为推断。

### 6.4 诊断与忠实改写

```text
POST   /resumes/{resume_id}/jobs/{job_id}/diagnostics
GET    /resumes/{resume_id}/jobs/{job_id}/diagnostics/{id}
POST   /optimization/issues/{issue_id}/select-strategy
POST   /optimization/issues/{issue_id}/rewrite-preview
POST   /resume-patches/{proposal_id}/confirm-facts
POST   /resume-patches/{proposal_id}/apply
POST   /resume-patches/{proposal_id}/reject
GET    /resume-patches/{proposal_id}/fidelity
```

诊断响应至少分为：

- `expression`；
- `evidence`；
- `capability`；
- `hard_constraint`；
- `consistency`；
- `structure_ats`；
- `relevance`；
- `differentiation`；
- `career_narrative`；
- `privacy_compliance`。

界面展示多个问题并按 blocker/high/medium/low 排序。

改写预览的核心文案结构：

```json
{
  "observation": "看到你在项目 X 中负责过用户访谈，并有访谈记录和需求文档。",
  "job_connection": "目标岗位要求用户研究和需求分析。",
  "suggested_text": "……",
  "source_claim_ids": ["..."],
  "source_evidence_ids": ["..."],
  "target_requirement_id": "...",
  "atomic_changes": [],
  "fidelity_status": "ready"
}
```

### 6.5 AI 面试官

```text
POST   /interview-sessions
GET    /interview-sessions/{session_id}
POST   /interview-sessions/{session_id}/next-question
POST   /interview-sessions/{session_id}/answers
GET    /interview-sessions/{session_id}/observations
POST   /interview-observations/{observation_id}/confirm
POST   /interview-observations/{observation_id}/reject
POST   /interview-sessions/{session_id}/complete
POST   /interview-sessions/{session_id}/revoke
```

创建 session 时必须显式选择模式：

- `vault_builder`：构建职业记忆；
- `target_gap`：补目标岗位信息；
- `claim_clarification`：澄清具体 Claim；
- `practice`：模拟面试，不默认写回事实。

每次只追问一个主要不确定点。用户必须能够回答“不知道、记不清、不愿回答”。

### 6.6 招聘方批筛

```text
POST   /employer/jobs/{job_id}/screening-runs
POST   /employer/screening-runs/{run_id}/rules
POST   /employer/screening-runs/{run_id}/execute
GET    /employer/screening-runs/{run_id}
GET    /employer/screening-runs/{run_id}/results
GET    /employer/screening-results/{result_id}
POST   /employer/screening-results/{result_id}/mark-reviewed
POST   /employer/screening-results/{result_id}/clarification
```

执行固定顺序：

1. 合法硬条件；
2. 招聘方选择的关键词；
3. taxonomy 同义词和标准化；
4. LLM 证据汇总与一致性分析；
5. 人工复核。

API 不接受客户端提交最终 LLM 结论或自动淘汰开关。

---

## 7. 前端信息架构

### 7.1 候选人导航

建议一级入口：

- 我的职业档案
- Evidence Vault
- 目标岗位
- 简历与诊断
- AI 面试官
- 投递记录
- 设置与数据控制

### 7.2 Career Passport 页面

包含：

- 职业时间线；
- 当前开放的待澄清 Claim；
- 最近使用的 Claim；
- 每次投递的不可变快照；
- Claim 修订历史；
- Claim 简化聊天抽屉；
- Evidence 关系；
- 分享范围。

状态文案使用：

- 用户已确认；
- 有用户证据支持；
- 信息不足；
- 存在待澄清的不一致；
- 招聘方已复核；
- 第三方已验证；
- 已撤回。

### 7.3 Evidence Vault Map

前端可使用图组件，但必须满足：

- 大量节点时按类型、时间和岗位过滤；
- 支持键盘和列表替代视图；
- 节点颜色不能暗示人的好坏或可信度；
- 冲突关系使用中性文案；
- 点击边可查看关系来源；
- 支持移动端退化为分组列表；
- 不把私有节点发送给无权限角色。

### 7.4 目标岗位与顾问页面

四层信息分别显示：

1. **这个企业这个岗位明确要求什么**；
2. **该职业通常需要什么**；
3. **公司公开业务和工作语境是什么**；
4. **市场中出现了什么趋势**。

不得混成一个“公司人才画像”。

顾问使用候选人 Evidence 时显示：

- “你已有且有证据”；
- “你可能具备，需要澄清”；
- “当前材料未观察到”；
- “需要真实提升”；
- “存在硬门槛”。

### 7.5 全面诊断页面

默认展示问题总览和多个问题，不只突出一条：

- 阻断问题；
- 高影响问题；
- 增强问题；
- 可选优化。

每个 issue 必须显示：

- 问题类型；
- 为什么是问题；
- 对应 JD；
- 当前使用的 Claim/Evidence；
- 推荐路径和其他路径；
- 能否直接写回；
- 改写依据；
- 结构化决策路径；
- 下一步。

### 7.6 AI 关闭选项

设置中提供：

- 全局关闭 AI；
- 关闭简历生成；
- 关闭 AI 面试；
- 关闭顾问聊天；
- 关闭招聘方 LLM 分析分享；
- 独立的模型改进 opt-in，默认关闭。

关闭后界面显示哪些功能仍可用，而不是仅显示错误。

### 7.7 招聘方批筛页面

页面分为：

1. 硬性条件配置；
2. 关键词选择；
3. 批次执行进度；
4. 筛选结果；
5. 人工复核队列；
6. 澄清请求；
7. 决策审计。

结果卡显示：

- 硬条件 pass/fail/unknown；
- 关键词命中；
- 对应岗位要求的证据；
- 缺失信息；
- 一致性问题；
- 合理替代解释；
- 建议追问；
- 人工复核状态。

不显示总体可信度分数。

---

## 8. AI Model Gateway

### 8.1 供应商选择

中国大陆邀请试用版推荐：

- 主要网关：阿里云百炼 / Model Studio，北京地域和独立 Workspace；
- 默认模型族：Qwen，具体模型由内部评测选择，不写死在业务代码；
- 复杂二次分析：可选同地域、合同允许的高能力模型；若使用 DeepSeek V4，必须确认具体调用地域、数据条款和当前模型 ID；
- Embedding/Reranker：通过相同网关或经评测的自托管模型；
- 规则层：不依赖 LLM。

不得继续默认使用已下线的 `deepseek-chat`。

### 8.2 代码结构

建议新增：

```text
backend/app/ai/
  gateway.py
  task_profiles.py
  schemas.py
  privacy_filter.py
  retries.py
  audit.py
  providers/
    base.py
    openai_compatible.py
    aliyun_model_studio.py
```

业务模块只能调用任务能力：

```python
await gateway.run(
    task="claim_extraction",
    payload=...,
    schema=ClaimExtractionResponse,
    context=InvocationContext(...),
)
```

业务模块不得直接读取供应商 API key、base URL 或具体模型名。

### 8.3 任务 profile

至少定义：

- `resume_parse`
- `jd_parse`
- `claim_extract`
- `claim_evidence_assess`
- `interview_question_render`
- `interview_observation_extract`
- `faithful_rewrite`
- `advisor_answer`
- `screening_evidence_summary`
- `consistency_alternative_explanations`

每个 profile 声明：

- model alias；
- temperature；
- max tokens；
- JSON Schema；
- timeout/retry；
- 是否允许 thinking mode；
- PII 字段策略；
- fallback 行为；
- prompt version；
- 费用和速率限制。

### 8.4 安全输出

1. 使用结构化输出；
2. Pydantic/JSON Schema 严格校验；
3. 拒绝未知字段或超长内容；
4. 所有 ID 由服务端重新验证；
5. Function call 参数必须重新授权；
6. JSON 为空或不合法时重试一次，随后返回可恢复错误；
7. 不得以规则虚构内容作为模型错误 fallback；
8. 供应商错误不能导致原数据被覆盖；
9. prompt injection 内容只作为候选人/企业数据，不作为系统指令；
10. 日志默认不记录完整简历、回答和 Evidence 原文。

### 8.5 建议环境变量

```text
AI_ENABLED=true
AI_PRIMARY_PROVIDER=aliyun_model_studio
AI_PRIMARY_BASE_URL=
AI_PRIMARY_API_KEY=
AI_DATA_REGION=cn-beijing
AI_MODEL_RESUME_PARSE=
AI_MODEL_INTERVIEW=
AI_MODEL_REWRITE=
AI_MODEL_REASONING=
AI_MODEL_EMBEDDING=
AI_MODEL_RERANK=
AI_REQUEST_TIMEOUT_SECONDS=
AI_MAX_RETRIES=
AI_AUDIT_CONTENT_LOGGING=false
```

旧 `DEEPSEEK_*` 在过渡期只允许映射到 Gateway，之后移除。`.env.example` 不能含真实 key。

### 8.6 模型评测后再定型号

至少使用：

- 200 个简历/JD 解析样本；
- 300 个 Claim–Evidence 关系样本；
- 200 个忠实改写样本；
- 150 个面试轮次；
- 200 个 HR 筛选案例。

比较：

- Schema 通过率；
- unsupported atomic fact rate；
- source link 准确率；
- 追问相关性和重复率；
- 专家一致率；
- 延迟；
- 单任务成本；
- 中文岗位覆盖；
- 不同岗位和候选人群体的错误差异。

型号配置由评测报告决定，不由厂商 benchmark 直接决定。

---

## 9. 真实、合法、有效的数据方案

### 9.1 数据来源层级

| 层级 | 数据 | 产品角色 |
|---|---|---|
| A | 企业提交并确认的 JD、岗位分析 | 企业岗位要求真相源 |
| B | 中国职业分类、职业技能标准、ESCO、O*NET | 职业通用参考和技能归一化 |
| C | 公司官网、年报、交易所披露、官方技术博客和官方开源仓库 | 公司公开语境 |
| D | 取得许可的聚合招聘数据 | 市场趋势 |
| E | 论坛和公开讨论 | 非代表性定性线索 |

层级 E 不进入正式岗位画像、候选人筛选、模型分数或录用建议。

### 9.2 画像生成规则

最终对用户展示四个独立对象：

#### Target Role Profile

来源：企业 JD 和企业确认的 Job Analysis。  
用途：诊断、匹配、筛选和行动路径。

#### Occupation Profile

来源：中国职业分类和职业技能标准，ESCO/O*NET 作为跨语言补充。  
用途：说明职业共性、技能邻接和成长路径。  
限制：不能覆盖企业 JD。

#### Company Context Profile

来源：企业官网、年报、正式披露、官方技术资料。  
用途：帮助用户理解业务和工作语境。  
限制：不能宣称公司一定偏好某类候选人。

#### Market Signal Profile

来源：经授权、去标识化、聚合后的岗位数据。  
用途：技能出现频率、地区和行业趋势。  
限制：不代表具体企业。

### 9.3 数据接入流程

每个来源必须经过：

```text
登记来源
→ 许可和用途审查
→ 获取固定版本
→ 保存 checksum 与原始快照
→ 解析和质量校验
→ 人工抽样
→ 发布 source version
→ 生产读取
→ 到期复核/撤销
```

未经批准的来源不得因“公开可访问”自动接入。

### 9.4 改写能力的数据

第一阶段不微调基础模型。建立专家金标集：

```text
目标 JD
+ 候选人 Evidence Bundle
+ 原始简历
+ 合格改写
+ 不合格改写
+ 不合格原因
+ 每个原子事实的 source refs
+ 专家复核结果
```

数据来源：

- 付费委托资深招聘人员和职业顾问；
- 签署数据、保密和知识产权授权；
- 使用虚构或彻底去标识化案例；
- 模型可生成负例，但必须由专家审核；
- 用户数据默认只服务该用户；
- 用于公共模型改进必须独立 opt-in。

禁止直接使用来源不明的简历数据集、抓取简历、私人消息或未授权企业候选人资料。

### 9.5 AI 面试能力的数据

通过岗位专家和资深 HR 工作坊形成：

- Job Analysis；
- Competency Rubric；
- 固定核心题；
- 合法追问；
- 评分锚点；
- 信息不足案例；
- 冲突与合理解释案例；
- 不应询问的问题；
- 升级人工复核条件。

专家经验必须转为结构化标签：

- observed claim；
- evidence present/missing；
- inconsistency type；
- alternative benign explanations；
- next question；
- employer-defined hard constraint；
- human-review requirement。

不采集或训练原始“隐性思维链”。真实面试 transcript 只有在独立同意、目的限定和可撤回前提下使用。

### 9.6 训练数据治理

每条训练/评测样本记录：

- dataset ID/version；
- source ID；
- lawful basis/contract；
- allowed use；
- de-identification method；
- annotator IDs；
- 双人标注和分歧裁决；
- quality status；
- train/dev/test split；
- deletion linkage；
- created/expired 时间。

同一候选人、同一公司模板和近似 JD 不得泄漏到不同 split。

---

## 10. 资深 HR Agent 的正确实现

本功能定位：

> 将资深 HR 的岗位分析、证据检查、替代解释和追问流程结构化，辅助招聘人员复核候选人材料。

它不能承诺保证简历真实性。

### 10.1 专家知识采集

每类岗位至少邀请 2–3 名有真实招聘经验的专家，使用相同案例独立标注，再裁决：

1. 岗位真正必要的硬条件；
2. 哪些内容只是 preferred；
3. 简历中哪些信息足以支持某项 requirement；
4. 什么是信息不足；
5. 什么是一致性问题；
6. 有哪些非欺骗性的合理解释；
7. 下一步应该问什么；
8. 什么情况下必须人工或外部验证；
9. 什么问题不合法、不相关或不应询问。

不以历史“录用/淘汰”直接作为正确答案。

### 10.2 推理流水线

```text
Employer-confirmed Job Requirements
    ↓
Deterministic Hard Filters
    ↓
Selected Keywords + Taxonomy
    ↓
Evidence Retrieval
    ↓
LLM Structured Summary
    ↓
Consistency Rules + Alternative Explanations
    ↓
Human Review
    ↓
Optional Claim Clarification
```

LLM 只能处理最小必要的、已授权的数据。能使用 Claim/Evidence 摘要时，不发送整个私人 Vault。

### 10.3 决策路径示例

```json
{
  "requirement": "三年以上 B2B 销售经验",
  "observations": [
    {"source": "claim-1", "text": "经历 A 明确包含两年 B2B 销售"},
    {"source": "claim-2", "text": "经历 B 未说明客户类型"}
  ],
  "rules_fired": ["hard_requirement_evidence_incomplete"],
  "finding": "当前材料只能确认两年，不能确认是否达到三年",
  "alternative_explanations": ["经历 B 可能包含 B2B 客户，但尚未说明"],
  "next_question": "经历 B 的客户对象和持续时间是什么？",
  "status": "needs_clarification",
  "human_review_required": true
}
```

---

## 11. PR10–PR17 实施顺序

## PR10：模型失效、无证据生成与数据来源 P0

### 目标

确保任何生产路径不再依赖已下线模型，不再在缺少模型或证据时生成虚构内容，并建立统一 Model Gateway 和 DataSourceRegistry。

### 数据库

- 新增 `data_sources`、`data_source_versions`；
- 新增 `ai_invocations`；
- 添加必要枚举和索引；
- 不删除旧字段。

### 后端

- 实现 Gateway 最小骨架；
- 迁移 `llm_client.py`、`interview.py`、`resume_variants.py` 到 Gateway；
- 移除所有自动补技能、角色、数字、结果的 fallback；
- 缺少 AI 配置时返回明确的 AI unavailable，但规则功能继续；
- 加入严格 Schema、超时、重试、审计和内容日志关闭；
- 为来源登记实现 admin-only API；
- 将 forum benchmark 标记为 E 层，不允许进入正式画像。

### 前端

- 正确显示 AI 不可用和规则功能仍可用；
- 不显示虚构 fallback 的结果；
- 管理端可查看来源状态，不展示敏感合同内容。

### 测试

- 无 API key 时不新增任何简历事实；
- 模型返回非法 JSON 时不写库；
- 模型返回未知 ID 时被拒绝；
- prompt injection 不能改变系统任务；
- revoked/pending 来源不能用于画像；
- 日志中不出现完整简历和 Evidence；
- 当前旧模型名不再是默认值。

### 完成门禁

- unsupported new fact 测试为 0；
- 所有直接 AsyncOpenAI/供应商调用均通过白名单审计，只允许 provider adapter；
- 完整后端、前端、迁移和安全测试通过。

## PR11：Career Passport 与 Evidence Vault Map

### 目标

把 Resume 附属 Claim 扩展为候选人的长期职业记录，并提供真正可用的记忆网络。

### 数据库

- 新增 `career_experiences`、`evidence_artifacts`、`resume_versions`、`resume_version_claim_links`；
- 扩展 ResumeClaim 和 ClaimEvidence；
- 数据回填和孤儿报告；
- down migration 不删除用户原始数据；若无法无损降级必须明确不可逆步骤并先获确认。

### 后端

- 新 Career Passport 和 Vault API；
- 旧 Claim API 调用同一 service；
- map API 服务端过滤节点和边；
- artifact 上传安全；
- Claim 合并、拆分、修订和撤回事件；
- ResumeVersion 创建服务。

### 前端

- Passport 时间线；
- 四种 Map 视图；
- Claim 详情与历史；
- Evidence 上传、绑定、撤回和分享；
- 简化 Claim chat 外壳，AI 能力在 PR12 接入。

### 测试

- Claim ID 迁移前后稳定；
- 跨租户不可读取；
- 招聘方只见 application snapshot；
- Map 不泄露隐藏节点；
- Evidence 撤回后不能被新改写使用；
- 历史 ResumeVersion 不变；
- 大图分页和移动端列表 fallback。

## PR12：结构化 AI 面试官与 Claim 澄清聊天

### 目标

将 Evidence Follow-up 合并到 AI 面试官，同时保留 Claim 的轻量聊天入口。

### 数据库

- 新增 session/question/answer/observation；
- 迁移或链接旧 InterviewResult；
- 保存 consent snapshot。

### 后端

- 四种模式；
- 问题目标由规则选择，LLM 只负责自然表达；
- 回答 observation span 抽取；
- 用户逐条确认；
- practice 与真实 Claim 默认隔离；
- 允许拒答和停止追问；
- 目的撤回和删除。

### 前端

- 明确显示当前模式；
- 问题目标和进度；
- Observation 确认页；
- Claim chat 调用同一澄清 service；
- 用户可关闭 AI 或退出。

### 测试

- 模拟回答不会自动成为 Claim；
- 未确认 observation 不能写简历；
- 回答 offset 可回到原文；
- 同岗位核心题一致；
- 重复追问终止；
- 禁止敏感/歧视问题；
- 撤回后停止后续使用。

## PR13：目标岗位优先的全面诊断、忠实改写和岗位准备度

### 目标

实现“先选岗位 → 从 Vault 检索 → 全面诊断 → 追问或忠实改写 → 行动路径”。

### 数据库

- 新增 OptimizationIssue、StrategyOption、ReadinessAction、ResumePatchProposal；
- 将 PR9 event 与实体关联；
- Potential Score UI/API 兼容映射到 readiness。

### 后端

- 生成多类别、多问题诊断；
- 复用 PR9 issue/strategy 枚举；
- Evidence Vault 检索；
- “看到你有……可以这样写……”输出；
- 原子变化和 Fidelity Proof；
- apply 时二次门禁并生成 ResumeVersion；
- current 与 future readiness 分离；
- 删除 credibility score 输出；
- Potential Simulation 作为 readiness 的反事实子功能保留。

### 前端

- 四栏工作流；
- 多问题总览；
- 改写依据和结构化决策路径；
- diff 和逐条确认；
- 岗位准备度与行动路径；
- 不使用录用概率文案。

### 测试

- 未选择岗位不能生成岗位定制改写；
- JD 不能成为候选人经历来源；
- 新数字/角色/技能被拦截；
- 多个问题完整展示；
- evidence gap 不误变 capability gap；
- 未来行动不提高 current；
- 组合 action 由同一评分器重算；
- apply 生成新 ResumeVersion，不覆盖历史。

## PR14：四层画像、合法数据流水线与 AI 求职顾问

### 目标

用真实来源构建目标岗位信息，并通过 AI 顾问帮助用户提高岗位相关性和准备度。

### 数据库

- 新增 TargetRoleProfileSnapshot、JobRequirement；
- 完善 DataSource version；
- 保存 advisor citations 和 response trace。

### 后端

- 企业 JD 解析和企业确认；
- 接入固定版本中国职业 taxonomy；
- 正式接入 ESCO/O*NET 前核对许可证和 attribution；
- 公司公开语境 RAG；
- 市场信号只读取 approved D 层；
- 顾问回答强制 source type 和 citations；
- 缓存和 freshness。

### 前端

- 四层画像明确分区；
- 顾问聊天；
- 来源、日期、版本和推断标识；
- 岗位准备度行动建议；
- 过期来源警告。

### 测试

- taxonomy 不覆盖企业 JD；
- 公司年报不变成招聘偏好；
- forum 不进入岗位判断；
- 每条顾问事实有 citation；
- revoked source 从后续结果移除；
- 相同 snapshot 可复现。

## PR15：资深 HR 批筛与一致性复核

### 目标

实现硬条件 → 关键词 → LLM → 人工复核的招聘方流程。

### 数据库

- 新增 ScreeningRun、Rule、Result；
- DecisionTrace；
- 将旧 CredibilityAuditRecord 作为兼容读取，停止创建 risk score；
- 迁移 UI 和 API 到中性状态。

### 后端

- 硬条件规则引擎；
- 关键词和 taxonomy；
- LLM 证据摘要；
- 一致性规则、替代解释和建议追问；
- 人工复核；
- Claim 澄清联动；
- 不允许自动变更终态。

### 前端

- 批筛配置和执行；
- 结果分层；
- 决策路径；
- 合理解释；
- 人工复核和澄清；
- 删除可信度分数。

### 测试

- 未授权简历不能进入 run；
- 敏感属性无法配置；
- unknown 不当作 fail；
- LLM 不能自动淘汰；
- 结果可追溯到 requirement 和 Claim snapshot；
- 招聘方之间严格隔离；
- 冲突文案不出现造假判断。

## PR16：用户控制、隐私、合规与成品体验

### 目标

使产品达到邀请制真实试用所需的用户控制、透明、申诉、删除和运维标准。

### 功能

- 全局和模块级 AI 开关；
- 四类用途同意；
- 下载、更正、撤回、删除；
- 数据保留与自动清理；
- AI 生成内容标识；
- 自动化辅助说明；
- 招聘方主体与职位核验；
- 投诉、申诉和人工联系；
- 管理后台、速率限制、告警；
- 空状态、异常恢复、移动端和无障碍；
- 隐私政策、用户协议、AI 功能说明；
- 根据实际业务模式完成法律顾问审查和备案/资质检查清单。

### 测试

- AI off 零模型调用；
- consent 分别撤回；
- 删除覆盖原件、文本、向量和允许删除的派生数据；
- 历史合规审计保留最小必要内容；
- 申诉可关联具体筛选结论；
- 内容标识和解释入口存在；
- 企业未核验时不能发起真实筛选。

## PR17：评测、红队、校准和邀请制发布门禁

### 目标

用足够强的证据证明产品可以交给真实试用者。

### 金标集

- 200 份 JD/简历结构化抽取；
- 300 组 Claim/Evidence 关系；
- 200 组忠实改写；
- 150 组结构化面试；
- 200 组 HR 筛选；
- 覆盖技术、产品、运营、设计、研究、管理、销售和应届项目。

### 发布指标

- 无支持的新事实：0；
- Schema 通过率 ≥ 99.5%；
- 硬事实 source coverage = 100%；
- Claim source link 准确率 ≥ 95%；
- 硬条件规则漏判率 ≤ 1%；
- 敏感属性进入筛选决策 = 0；
- LLM 自动淘汰 = 0；
- AI 关闭后的模型调用 = 0；
- 重要输出可追溯率 = 100%；
- 相同版本输入可复现率 ≥ 99%；
- 删除任务完成率 = 100%；
- 所有权限和跨租户回归通过。

### 人工评审

至少包括：

- 资深招聘从业者；
- 职业顾问；
- 候选人代表；
- 数据安全人员；
- 中国法律顾问；
- 未参与开发的试用者。

任何真实世界校准和人工评审尚未发生时，PR17 只能标记部分完成。

---

## 12. 测试策略

### 12.1 单元测试

- Fidelity 原子变化；
- issue 分类；
- evidence/capability 分离；
- hard filter；
- taxonomy 归一化；
- source 状态门禁；
- consent 和 AI off；
- decision trace 生成；
- Schema validation；
- retry/fallback。

### 12.2 集成测试

- Candidate A/B、Employer A/B 跨租户；
- Vault → Interview → Claim → Rewrite → ResumeVersion；
- JD → Profile → Diagnostic → Action；
- Application Snapshot → Employer Screening → Clarification；
- Evidence 撤回和数据删除；
- provider failure；
- migration upgrade/down/upgrade。

### 12.3 PostgreSQL 并发测试

- 同一 Claim 并发回答；
- 同一 patch 并发 apply；
- 同一 screening run 重复 execute；
- 同一 Evidence 撤回与读取；
- ResumeVersion number；
- 幂等键；
- 使用行锁或唯一约束证明无重复/丢失。

### 12.4 前端测试

- 术语和禁止文案；
- 多问题展示；
- AI off；
- 四种 interview mode；
- Map 列表 fallback；
- 招聘方批筛；
- 权限错误；
- 加载、空状态和恢复；
- 移动端。

### 12.5 浏览器 E2E

至少覆盖：

1. 候选人导入 JD；
2. 从 Vault 发现相关经历；
3. 看到多个诊断问题；
4. 对 evidence gap 进入面试；
5. 确认 observation；
6. 生成带依据的 rewrite；
7. Fidelity 通过后生成新版本；
8. 查看岗位准备度行动路径；
9. 投递并创建快照；
10. 招聘方批筛和发起澄清；
11. 候选人关闭 AI 后继续人工流程。

### 12.6 红队

- prompt injection；
- 恶意 JD 要求使用敏感属性；
- 客户端篡改 Claim/evidence ID；
- 篡改 `can_apply_now`；
- 大量原文加少量虚构和少量原文加大量虚构；
- 文本中隐藏职位/数字指令；
- 跨租户 ID 枚举；
- 过期签名 URL；
- 删除后向量残留；
- LLM 输出“候选人造假”；
- 用练习回答写入真实简历；
- forum 结论冒充企业要求。

---

## 13. 合规和产品表述

本文件不是法律意见。正式邀请真实用户前，必须由中国法律顾问结合实际部署和业务模式审核。

### 13.1 产品表述

允许：

- 履历证据库；
- Claim Passport；
- 信息不足；
- 有用户证据支持；
- 第三方已验证；
- 存在待澄清的一致性问题；
- 岗位准备度；
- 模型内相对变化；
- AI 辅助，最终由人工决定。

禁止：

- 简历真实性保证；
- 造假概率；
- 测谎；
- 可信度分数；
- AI 保证筛选真实候选人；
- Offer 概率；
- 保证提高录用率；
- AI 自动决定录用或淘汰。

### 13.2 需核对的合规项目

- 个人信息处理目的、最小必要和单独同意；
- 敏感个人信息；
- 自动化决策说明、拒绝和人工复核；
- 用户访问、更正、删除和撤回；
- 数据出境和处理地域；
- 模型供应商合同和数据使用条款；
- 生成内容标识；
- 招聘主体和职位真实性核验；
- 网络招聘服务相关资质和信息留存；
- 算法备案、安全评估或其他适用要求；
- 投诉和申诉机制；
- 数据泄露应急响应。

---

## 14. 可观测性与运营

不得在日志和指标标签中记录完整简历、回答或 Evidence。

必须监控：

- 各 AI task 成功率、Schema 错误率、延迟和成本；
- unsupported fact 拦截次数；
- Evidence follow-up 完成率；
- rewrite 预览/确认/拒绝率；
- AI off 使用率；
- issue 类型分布；
- evidence gap → capability gap 误判抽检；
- 招聘方 unknown/fail 分布；
- 人工推翻 AI finding 的比例；
- 不同岗位和群体的错误差异；
- 数据删除队列；
- revoked source 使用告警；
- 跨租户访问拒绝；
- 投诉和申诉 SLA。

监控指标不能反向成为未经同意的训练数据。

---

## 15. 每个 PR 的固定交付格式

Cursor 完成每个 PR 后必须提交一份 `PRxx_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`，包含：

1. 本 PR 目标和明确不包含的范围；
2. 需求追踪矩阵；
3. 修改文件与原因；
4. 数据模型和迁移；
5. API/前端行为变化；
6. 权限和隐私影响；
7. 模型、prompt、schema、rule 版本；
8. 新增和修改的测试；
9. 实际执行命令和原始结果摘要；
10. PostgreSQL upgrade/down/upgrade 结果；
11. 浏览器人工/E2E 证据；
12. 兼容性与回滚；
13. 未完成事项和风险；
14. 确认未覆盖任务开始前的用户改动；
15. 最终判定：完成/部分完成/阻断。

---

## 16. 第二轮最终完成定义

PR10–PR17 全部完成并不只代表代码存在。必须证明：

- 候选人可使用长期 Career Passport；
- Evidence Vault 是可操作、可追溯、受权限保护的记忆网络；
- AI 面试官能进行结构化追问，且练习与事实隔离；
- 用户先选岗位，再完成全面诊断和忠实改写；
- 所有改写都有来源和 Fidelity；
- 岗位准备度与行动路径替代 Potential/Credibility 分数；
- 顾问使用四层、真实、合法、版本化的数据；
- 招聘方实现硬条件 → 关键词 → LLM → 人工流程；
- AI 不做测谎或自动淘汰；
- 用户可关闭 AI、撤回授权和删除数据；
- 模型供应商可替换，已下线模型不再阻断产品；
- 评测和真实人工验收达到 PR17 门禁；
- 法律、隐私、安全和运维清单已由相应负责人签字。

任一项目缺失都不能宣称第二轮完成或“商业化成品”。

---

## 17. 研究和官方资料

技术和数据实现前应重新核对这些页面的当前版本，不要仅依赖本文日期：

- DeepSeek API 更新记录：<https://api-docs.deepseek.com/updates/>
- DeepSeek JSON Output：<https://api-docs.deepseek.com/zh-cn/guides/json_mode/>
- 阿里云 Model Studio 隐私说明：<https://help.aliyun.com/zh/model-studio/privacy-notice>
- 阿里云地域和部署：<https://help.aliyun.com/zh/model-studio/regions/>
- Qwen 结构化输出：<https://help.aliyun.com/zh/model-studio/qwen-structured-output>
- Qwen Function Calling：<https://help.aliyun.com/zh/model-studio/qwen-function-calling>
- 中国职业分类大典（2022）：<https://www.mohrss.gov.cn/wap/xw/rsxw/202207/t20220714_457800.html>
- ESCO 数据和 API：<https://esco.ec.europa.eu/en/use-esco>
- O*NET Database：<https://www.onetcenter.org/database.html>
- OPM Structured Interviews：<https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews/>
- OPM Job Analysis：<https://www.opm.gov/policy-data-oversight/assessment-and-selection/job-analysis/>
- CIPD Selection Methods：<https://www.cipd.org/uk/knowledge/factsheets/selection-factsheet/>
- 《个人信息保护法》：<https://www.miit.gov.cn/jgsj/zfs/fl/art/2022/art_515a4b20c12f430eab54bb4f56d89f56.html>
- 《生成式人工智能服务管理暂行办法》：<https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm>
- 《人工智能生成合成内容标识办法》：<https://www.cac.gov.cn/2025-03/14/c_1743654685899683.htm>

公开可访问不等于可以批量复制、再分发或用于训练。Cursor 不能自行替代许可审查。

---

## 18. 可直接复制给 Cursor 的首轮指令

```text
完整阅读 CURSOR_SECOND_ROUND_PRODUCT_IMPLEMENTATION_SPEC.md、CURSOR_DEFINITION_OF_DONE.md、CURSOR_EXECUTION_BACKLOG.md、AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md、PR8_IMPLEMENTATION_AND_VERIFICATION_REPORT.md、PR9_IMPLEMENTATION_AND_VERIFICATION_REPORT.md 和当前 git status。

这是第二轮产品化改造。不得一次实现 PR10–PR17，也不得重新建立平行的 Claim、Evidence、Suggestion、Interview 或评分系统。

本轮只执行 PR10。第一步只能做只读差距审计：
1. 逐项核对 PR10 目标、数据库、后端、前端、测试和完成门禁；
2. 输出“已满足/部分满足/未满足”需求追踪矩阵，并给出当前文件和行号；
3. 列出所有直接模型调用、旧 deepseek-chat 默认值、无证据 fallback、自动补技能/数字/结果路径、forum benchmark 的正式消费路径；
4. 设计 Model Gateway、DataSourceRegistry、迁移、兼容、回滚、隐私裁剪和测试；
5. 检查现有工作区改动，禁止覆盖用户资产。

完成审计后再按测试优先实现 PR10。任何 AI 输出都不能直接成为候选人事实、造假结论或自动招聘决定。模型不可用时不得生成虚构 fallback。完成后严格按本规格第 15 节生成 PR10 实施与验收报告；任一门禁缺失只能报告“部分完成”。
```

后续每个 PR 使用同样模式：把上方“PR10”替换为明确指定的当前 PR，并仅实施该批次。

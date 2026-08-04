# QLink 第三轮产品改造：Cursor 可执行实施规格

> 文档版本：2026-08-03  
> 适用仓库：`ai-job-platform`  
> 实施代号：R3-00～R3-06  
> 文档用途：Cursor 每次选择一个工作包，按本文完成差距审计、迁移、编码、测试和验收  
> 第三轮目标：把第二轮已经存在的 Career Passport、Evidence Vault、目标岗位诊断、结构化访谈和行动计划，编排成一条“岗位要求 → 证据 → 正确下一步 → 当前可用申请包”的候选人主流程
> 首发市场：中国大陆求职市场  
> 首发岗位：互联网与 AI 知识型岗位，优先覆盖软件工程、AI 应用工程、数据分析/数据科学、互联网/AI 产品四个岗位族  
> 首批用户：未来 1–3 个月正在真实求职、拥有至少两段可挖掘经历、能够提供真实目标 JD 的应届生和工作三年内候选人

---

## 0. 给 Cursor 的最高优先级指令

开始任何修改前，完整阅读：

1. 本文件 `CURSOR_THIRD_ROUND_IMPLEMENTATION_SPEC.md`；
2. `NEXT_ITERATION_EXECUTABLE_PRODUCT_PLAN.md`；
3. `CURSOR_SECOND_ROUND_PRODUCT_IMPLEMENTATION_SPEC.md` 中的 INV-01～INV-10；
4. `CURSOR_DEFINITION_OF_DONE.md`；
5. 当前 `git status`；
6. 当前工作包涉及的模型、迁移、服务、路由、页面和测试。

执行规则：

1. **不得一次实现 R3-00～R3-06。** 用户没有指定工作包时，只做只读差距审计并建议从 R3-00 开始。
2. 工作区已有修改全部视为用户资产。禁止 `git reset`、`git checkout --`、覆盖或格式化无关文件。
3. 修改前输出：本包目标、需求追踪、涉及文件、迁移、兼容风险、测试计划。
4. 先写失败测试，再实现；每个工作包单独完成迁移、回滚、后端测试、前端测试和人工验收。
5. 不得新建与 `ResumeClaim`、`EvidenceArtifact`、`InterviewSession`、`JobRequirement`、`OptimizationIssue`、`ReadinessAction`、`ResumePatchProposal` 平行的重复系统。
6. 不得将“简历中没出现”直接解释为“候选人不具备”。只有用户明确确认没有相关经历或完成有效能力评估后，才能进入发展状态。
7. 所有 AI 产出都是待确认建议。不得写入未经确认的职责、技能、数字、客户、规模、结果或因果关系。
8. 岗位 JD、市场信息、职业词库和模型常识只能作为目标或语境，不能成为候选人经历的事实来源。
9. 不展示模型隐藏思维链。只保存结构化依据、规则、来源引用、不确定性和推荐动作。
10. 不实现自动淘汰、面试概率、Offer 概率、测谎、可信度评分、学校或名企偏好加分。
11. 所有写接口必须验证后端资源归属，并支持项目现有的 `Idempotency-Key` 语义。
12. 测试不得连接开发或生产数据库；PostgreSQL 并发测试只能使用隔离测试库。
13. 若一个工作包未达到本文门禁，只能报告“部分完成”，不得继续下一个工作包。

### 0.1 文档优先级

发生冲突时按以下顺序执行：

1. 安全、权限、隐私和事实忠实性不变量；
2. 本第三轮规格；
3. 第二轮规格中仍适用的 INV-01～INV-10；
4. `NEXT_ITERATION_EXECUTABLE_PRODUCT_PLAN.md`；
5. 旧战略和历史 PR 文档。

第三轮不取消第二轮 PR16/PR17。R3-00～R3-06 完成并稳定主流程后，才继续 PR16 用户控制/合规成品体验和 PR17 正式评测/发布门禁。

---

## 1. 第三轮要交付的产品

### 1.0 首发市场与客户边界

第三轮不是面向所有地区、所有年轻人和所有职业发布。首发边界固定为：

- **地区**：中国大陆求职市场；
- **岗位族**：软件工程（前端/后端/全栈）、AI 应用工程、数据分析/数据科学、互联网产品/AI 产品；
- **职业阶段**：应届、实习转正和工作三年内；
- **必要输入**：至少两段项目、实习、研究或工作经历，以及一份用户真实考虑申请的 JD；
- **核心场景**：用户需要判断每项岗位要求究竟已有证据、只是没有说清、需要真正发展，还是存在现实约束。

跨地区、海外签证、传统行业、蓝领岗位、高管岗位和完整转行规划不作为本轮发布承诺。系统可以保留通用数据结构，但试点招募、标注集、页面示例、岗位模板和发布判断必须遵守上述首发边界。

### 1.1 唯一核心能力

面对一项真实岗位要求，系统必须选择以下一个可执行状态：

| 状态 | 产品含义 | 用户下一步 |
|---|---|---|
| `supported` | 已有相关、已确认且足够具体的候选人证据 | 直接用于申请材料 |
| `clarify` | 有相关经历，但角色、方法、范围或结果缺失 | 当场回答一个问题 |
| `develop` | 澄清后由用户确认目前没有足够相关或可迁移证据 | 完成一个异步发展任务 |
| `constraint` | 签证、地区、证书、学历等客观条件满足、冲突或未知 | 单独确认或处理约束 |
| `unknown` | 信息不足、来源冲突或系统无法可靠判断 | 补充信息或保持未知 |

这不是静态分类器，而是下一步决策状态机。

### 1.2 候选人端主流程

```text
导入/确认背景
  → 选择“已有目标”或“探索方向”
  → 粘贴/导入外部真实 JD，或选择平台已有岗位
  → 提取 5–8 项关键要求
  → 为每项要求检索 Claim / Evidence / 已确认访谈观察
  → 生成五状态路由
  → 最多回答 3 个高价值澄清问题
  → 即时重算状态
  → 随时生成当前可用申请包
  → 将 develop 状态变成一个可回填任务
  → 记录投递、面试和结果
```

### 1.3 本轮成功的定义

本轮成功分为两层，工程完成不能代替商业成功。

**产品质量门禁：**

- 一个候选人可以在 `/candidate/advisor` 完成上述端到端流程；
- 首次可用产出中位时间不超过 5 分钟；
- 所有申请包内容均能追溯到用户材料；
- `clarify` 不会未经用户回答直接变成 `develop`；
- `unknown` 被允许存在；
- 当前算法与新路由可以离线对照；
- 不影响现有 Career Passport、Evidence Vault、投递、Interview 和 Employer Screening。

**商业成功门禁：**

- 20–30 名符合 1.0 定义的真实目标用户完成试点，每人使用一份真实 JD；
- 至少 70% 能指出系统改变的一个具体下一步，而不是只评价“内容不错”；
- 至少 50% 在 7 天内完成第二次有效行为：补充澄清、提交任务成果、生成第二份岗位分析或更新申请结果；
- 至少 5 名用户真实支付 ¥39–59，或支付同额、规则明确的可退试点押金；
- 相比“直接使用通用大模型分析同一份简历和 JD”的基线，下一步有用率提升至少 15 个百分点；
- 满足 R3-06 的事实忠实性和错误率门禁。

只有产品质量与商业成功两层同时通过，才能作出扩大用户试点或继续商业化的 `Go` 决策。只通过产品质量门禁时，结论只能是 `Iterate`，不得宣传为产品市场匹配。

### 1.4 本轮明确不做

- 市场情报数据库或实时劳动力市场预测；
- 课程/培训内容推荐平台；
- 图数据库迁移；
- 新建第二套招聘者筛选系统；
- 自动拒绝候选人；
- 训练基础模型或排序模型；
- 结果分析大屏；
- 正式支付收单、自动续费和套餐系统扩建；R3-06 的人工收费/可退押金实验属于必须完成的商业验证，不在此排除；
- 用虚构高校、企业或招聘机构背书产品。

---

## 2. 当前代码基线与复用边界

### 2.1 必须复用的后端对象

| 当前对象 | 第三轮用途 | 禁止做法 |
|---|---|---|
| `CareerExperience` | 用户长期经历 | 不新建第三轮经历表 |
| `ResumeClaim` | 原子化候选人陈述 | 不把模型推断直接写为 Claim |
| `EvidenceArtifact` / `ClaimEvidence` | 证据和 Claim 关系 | 不用纯 JSON 替代既有证据归属 |
| `ResumeVersion` | 不可变简历版本 | 不覆盖历史投递版本 |
| `TargetRoleProfileSnapshot` | 岗位画像快照 | 不混入公司传闻或论坛结论 |
| `JobRequirement` | 路由的目标要求 | 不另建第三套岗位要求表 |
| `InterviewSession(mode='target_gap')` | 即时澄清会话 | 不另建聊天/问答系统 |
| `InterviewQuestion/Answer/Observation` | 问题、回答、可确认观察 | 回答未经确认不得写回 Claim |
| `OptimizationIssue` | 兼容第二轮诊断 | 不直接删除或破坏旧接口 |
| `ReadinessAction` | develop 状态的发展任务 | 不另建课程任务表 |
| `ResumePatchProposal` | 单项忠实改写 | 不绕开 Fidelity 检查 |
| `DecisionTrace` | 结构化决策依据 | 不保存 Chain-of-Thought |
| `ScreeningRun/Result` | 招聘者侧受控试点 | 第三轮不扩建招聘者主流程 |

### 2.2 必须复用的服务与页面

- `backend/app/career_vault.py`、`career_vault_routes.py`：背景、Claim、Evidence；
- `backend/app/target_job_optimization.py`：既有岗位诊断和忠实改写；
- `backend/app/interview_sessions.py`：澄清提问、回答、观察与确认；
- `backend/app/personalized_guidance.py`：发展任务文案；
- `backend/app/advisor.py`、`advisor_routes.py`：岗位画像、有来源回答，以及**已存在的候选人 JD 导入端点 `POST /advisor/target-jobs/import`**；
- `backend/app/matching_hybrid.py`：候选岗位召回与旧基线；
- `frontend/src/pages/Candidate/Advisor.jsx`：第三轮主工作台 URL 与页面壳；
- `TargetJobOptimizationPanel.jsx`：保留兼容，逐步把能力迁入新工作台；
- `PersonalizedGuidancePanel.jsx`：复用任务展示语义；
- `CareerPassport.jsx`、`EvidenceVault.jsx`：深度编辑入口，不复制到工作台。

### 2.3 已确认需要修正的旧算法

1. `matching_signals.py` 的名企经历行业补偿必须移除；
2. 面试/Offer 启发式概率必须从 API 正式响应和 UI 中删除；
3. “无量化数字”等于“影响力低”的规则不能参与路由真相；
4. `growth_potential` 的静态关键词、短年限+高职级规则不能作为能力判断；
5. `matching_preference.py` 默认 focused gate 不能阻断探索模式的相邻方向；
6. `matching_rerank.py` 不得向模型发送候选人姓名；应改为使用 Claim、项目、确认状态和证据来源；
7. 匹配总分只能作为旧基线和召回参考，不能直接映射五状态。

### 2.4 已确认需要修正的旧入口

首发 ICP 手里的 JD 来自外部招聘站点，不在平台岗位库中。以下四点是当前代码里会直接堵死该场景的事实，必须在实施 6.1A 前逐条处理，不得绕过：

1. **后端已有导入能力，前端没有入口。** `backend/app/advisor_routes.py` 的 `POST /advisor/target-jobs/import` 已支持 `description_text` 建私有岗位，但 `frontend/src` 中没有任何粘贴表单；`Advisor.jsx` 与 `TargetJobOptimizationPanel.jsx` 的目标岗位选择器都只读取 `GET /browse-jobs`。
2. **私有岗位会被岗位列表过滤掉。** `main.py` 的 `/browse-jobs` 排除 `parsed_json.advisor_private=true` 的岗位，`GET /job/{id}` 对私有岗位返回 404。若第三轮的目标岗位选择器沿用这两个接口，用户自己导入的 JD 反而选不到。必须新增按 owner 可见的私有岗位读取路径，且不得因此让私有岗位对其他用户可见。
3. **现有导入使用纯规则解析。** 该端点走 `parse_job_rules_only`，不保证能从任意外部 JD 稳定抽出 5–8 项可路由要求。6.1A 的要求抽取必须有独立质量门禁，见 R3-02 与 R3-06。
4. **私有岗位归属未被下游校验。** `target_job_optimization.py` 的 `owned_inputs` 只校验 Resume 归属，未校验私有岗位的导入者归属。所有以 `target_job_id` 为入参的第三轮接口必须补这条校验。

**不建平行系统：** 6.1A 必须复用上述端点的解析与建表逻辑（必要时把它抽成 `advisor.py` 或新模块中的共享函数并让两个路由同时调用），不得新写第二套 JD 解析器和第二张私有岗位表。

---

## 3. 第三轮不可破坏的不变量

### R3-INV-01：缺失文本不等于能力缺失

没有检索到关键词时，初始状态只能是 `clarify` 或 `unknown`。只有出现以下之一才能进入 `develop`：

- 用户对针对性问题明确选择“没有相关经历”；
- 用户确认的回答明确表明尚未实践该能力；
- 经用户同意的、定义明确的能力评估得出不足结论。

### R3-INV-02：支持状态必须有确认来源

`supported` 至少关联一项：

- 用户已确认的 Claim；
- 可用于简历辅助的 Evidence；
- 用户已确认的 InterviewObservation；
- 原简历中可定位的原文 Claim。

仅有模型相似度或 JD 关键词不能进入 `supported`。

### R3-INV-03：硬约束独立

签证、地点、证书、学历、工作模式等不得混入能力总分。必须输出满足、冲突或未知，并给出来源。

### R3-INV-04：状态转移可审计

每次状态变化必须记录：旧状态、新状态、触发类型、来源引用、规则/模型/Prompt/Schema 版本、操作者和时间。

### R3-INV-05：最多三个即时问题

一次工作流首轮最多向用户展示三个问题。排序依据为：安全错误成本、能否改变状态、岗位重要性、用户回答成本。

### R3-INV-06：部分生成不等于补全

申请包可以只包含 `supported` 内容。`clarify`、`develop`、`constraint`、`unknown` 只能显示为内部缺口说明，不得伪装成候选人经历导出。

### R3-INV-07：AI 关闭后仍可用

AI 关闭时必须支持：规则提取、手动选择目标、Claim/Evidence 检索、手动关联、手动回答、规则状态机和导出已确认内容。

### R3-INV-08：旧接口兼容

现有 PR11–PR15 API、测试和页面在第三轮迁移期间保持可用。新工作台内部可以调用旧服务，但不得要求一次性删除旧组件。

---

## 4. 目标领域模型

第三轮新增四类持久化对象，并扩展两类旧对象。所有表使用项目现有 SQLAlchemy、Alembic wrapper 和配套 up/down SQL 方式。

### 4.1 `OpportunityWorkflow`

文件：`backend/app/models_db.py`

建议表名：`opportunity_workflows`

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `id` | String(36) | UUID 主键 |
| `user_id` | FK users | 非空，候选人归属 |
| `resume_id` | FK resumes | 非空，当前背景容器 |
| `resume_version_id` | FK resume_versions | 可空，开始路由时固定 |
| `entry_mode` | String(16) | `target` / `explore` |
| `target_job_id` | FK job_descriptions | 选择目标前可空 |
| `target_job_source` | String(16) | `imported`（用户粘贴，默认路径）/ `platform`（平台岗位库）；路由后不可变 |
| `profile_snapshot_id` | FK target_role_profile_snapshots | 路由后非空 |
| `direction_snapshot` | JSON | Explore 三方向的不可变选择快照 |
| `status` | String(24) | `onboarding/routing/clarifying/ready/actioning/completed/abandoned` |
| `schema_version` | String(64) | 默认 `opportunity_workflow_v1` |
| `rule_version` | String(64) | 默认 `route_rules_v1` |
| `created_at/updated_at/completed_at` | datetime | 审计时间 |

索引：

- `(user_id, status, updated_at)`；
- `(user_id, target_job_id, created_at)`。

约束：

- `entry_mode='target'` 创建时允许直接带 `target_job_id`；
- `entry_mode='explore'` 可先为空，但执行 route 前必须选择真实岗位；
- 只能访问本人 Resume 和 Workflow；
- 已完成工作流不得静默换 Resume 或目标岗位，必须新建工作流。

### 4.2 `RequirementRoute`

建议表名：`requirement_routes`

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `id` | UUID | 主键 |
| `workflow_id` | FK opportunity_workflows | 非空 |
| `job_requirement_id` | FK job_requirements | 非空 |
| `route_state` | String(20) | 五状态之一 |
| `resolution_status` | String(20) | `pending/resolved/superseded` |
| `reason_code` | String(64) | 稳定机器码，不存自然语言逻辑 |
| `user_summary` | Text | 面向用户的简短解释 |
| `missing_fields` | JSON | 如 role/method/scope/result/evidence |
| `constraint_status` | String(16) | `pass/conflict/unknown/not_applicable` |
| `importance` | Integer | 固定自 JobRequirement 快照 |
| `initial_state` | String(20) | 首次路由状态，便于评测 |
| `source_snapshot_hash` | String(64) | 输入 Claim/Evidence/Answer 摘要哈希 |
| `decision_trace_id` | FK decision_traces | 非空 |
| `rule/model/prompt/schema_version` | String | 可复现版本 |
| `created_at/updated_at/resolved_at` | datetime | 时间 |

唯一约束：`(workflow_id, job_requirement_id, resolution_status)` 不适合直接使用，因为历史 superseded 可多条。第一版使用 `(workflow_id, job_requirement_id)` 唯一行并用事件表保存历史；重跑时更新当前行并追加事件。

### 4.3 `RequirementRouteSourceLink`

建议表名：`requirement_route_source_links`

字段：

- `id`；
- `requirement_route_id` FK；
- `source_type`：`claim/evidence/interview_observation/interview_answer/constraint_input`；
- `source_id`；
- `relation`：`supports/related/contradicts/answers`；
- `source_text_snapshot`：脱敏且长度受限的不可变摘要；
- `source_hash`；
- `candidate_confirmation_state`；
- `created_at`。

唯一约束：`(requirement_route_id, source_type, source_id, relation)`。

不得只保存模型生成摘要而丢失源对象 ID。

### 4.4 `RequirementRouteEvent`

建议表名：`requirement_route_events`，追加式、禁止更新。

字段：

- `route_id`；
- `workflow_id`；
- `event_type`；
- `from_state` / `to_state`；
- `trigger_type`：`initial_route/user_answer/user_confirmation/evidence_link/rule_recompute/manual_review/system`；
- `trigger_ref_type` / `trigger_ref_id`；
- `payload`：只放非敏感结构化数据；
- `rule/model/prompt/schema_version`；
- `actor_user_id`；
- `created_at`。

事件至少覆盖：`requirement_routed`、`clarification_asked`、`clarification_answered`、`route_resolved`、`development_task_created`、`route_superseded`。

### 4.5 `ApplicationPackageDraft` 与 Item

建议表：

- `application_package_drafts`；
- `application_package_items`。

Draft 字段：

- `id/user_id/workflow_id/job_id/resume_version_id`；
- `status`：`draft/exported/superseded`；
- `coverage_snapshot`：各状态数量和已覆盖 requirement IDs；
- `fidelity_status`：`ready/blocked`；
- `schema/prompt/model/rule_version`；
- `created_at/exported_at`。

Item 字段：

- `draft_id`；
- `item_type`：`resume_bullet/cover_letter_material/interview_story/internal_gap_note`；
- `content`；
- `field_path` 可空；
- `route_ids/source_claim_ids/source_evidence_ids/source_answer_ids` JSON；
- `fidelity_result` JSON；
- `usable_now` Boolean；
- `status`：`ready/needs_confirmation/excluded`；
- `created_at`。

导出接口只能导出 `usable_now=true AND status='ready' AND fidelity_result.ready=true` 的项目。`internal_gap_note` 永不进入对外材料。

### 4.5A 导入 JD 的持久化方式

6.1A 不新建岗位表。导入结果仍写入 `job_descriptions`，沿用现有私有岗位约定，并补齐以下字段（写入 `parsed_json`，或按需要新增列，二选一但必须在 R3-01 固定）：

| 键 | 含义 |
|---|---|
| `advisor_private` | 保持 `true`，不进入公开岗位列表 |
| `advisor_imported_by` | 导入者 user_id，所有下游接口据此校验归属 |
| `jd_text_hash` | 正文哈希，用于同一用户重复导入的幂等 |
| `source_url` / `source_platform` | 可空来源引用，只保存不抓取 |
| `requirements_confirmation_state` | `pending` / `confirmed`，未确认不得进入 `routes:build` |
| `launch_scope_status` | `in_scope` / `out_of_scope`，对应 1.0 首发岗位族 |

原文快照不可变：同一 `jd_text_hash` 的重复导入返回既有记录，不覆盖正文。用户修改要求只改 `JobRequirement`，不改 JD 原文。

### 4.6 扩展现有对象

#### `InterviewSession` / `InterviewQuestion`

- `InterviewSession` 增加可空 `workflow_id` FK；
- `InterviewQuestion` 增加可空 `requirement_route_id` FK；
- 继续使用 `mode='target_gap'`；
- 一个工作流首轮最多创建 3 个未回答核心问题；
- 旧 session 不受影响。

#### `ReadinessAction`

- 增加可空 `requirement_route_id` FK；
- 将 `issue_id`、`strategy_id` 改为可空；
- 增加数据库约束：来源必须是 `(issue_id + strategy_id)` 或 `requirement_route_id`，不能全部为空；
- develop 路由每次最多有一个 active action；
- action 完成不自动提高当前支持状态；必须提交 Evidence 或确认 Observation 后重算。

---

## 5. 状态机与路由规则

### 5.1 初始路由顺序

必须按顺序执行，禁止让 LLM 自由跳转：

1. 判断是否为客观约束；是则进入 `constraint`；
2. 检索已确认 Claim、Evidence、Observation；
3. 若存在足够且直接的已确认来源，进入 `supported`；
4. 若存在相关来源但缺 role/method/scope/result 等字段，进入 `clarify`；
5. 若没有相关来源，检查是否能提出一个用户可回答的“是否存在”问题：能则 `clarify`，不能则 `unknown`；
6. 初始运行不得进入 `develop`，除非数据库中已经存在该用户对同一要求的明确“目前没有”确认事件。

### 5.2 允许的状态转移

| From | Trigger | To |
|---|---|---|
| `unknown` | 找到相关 Claim/Evidence | `clarify` 或 `supported` |
| `clarify` | 用户回答并确认充分证据 | `supported` |
| `clarify` | 用户明确确认没有相关经历 | `develop` |
| `clarify` | 回答暴露客观限制 | `constraint` |
| `clarify` | 用户跳过或仍不足 | `unknown` |
| `develop` | 任务完成但未提交证据 | 保持 `develop` |
| `develop` | 新 Evidence/Claim 已确认 | `clarify` 或 `supported` |
| `constraint` | 用户更新约束输入 | `constraint`，仅子状态改变 |
| `supported` | 来源撤回、删除或冲突 | `clarify` 或 `unknown` |

禁止：

- `unknown → develop`（无用户确认）；
- `develop → supported`（只有任务勾选，无证据）；
- `clarify → supported`（回答尚未确认）；
- 任意状态因模型置信度变化直接覆盖，无事件记录。

### 5.3 路由器接口

新增：`backend/app/opportunity_evidence_router.py`

建议纯函数与服务边界：

```python
class RouteDecision(TypedDict):
    state: Literal["supported", "clarify", "develop", "constraint", "unknown"]
    reason_code: str
    user_summary: str
    missing_fields: list[str]
    source_refs: list[dict]
    constraint_status: str
    uncertainties: list[str]
    recommended_action: dict

def route_requirement(context: RequirementRoutingContext) -> RouteDecision: ...

async def build_or_refresh_workflow_routes(
    db: AsyncSession,
    *,
    workflow: OpportunityWorkflow,
    actor_user_id: str,
) -> list[RequirementRoute]: ...
```

LLM 可用于：

- 判断语义关联候选集合；
- 提取缺失字段；
- 生成简短、可回答的问题；
- 生成用户友好摘要。

LLM 不得决定：

- 是否允许进入 `develop`；
- 是否满足硬约束；
- 用户事实是否确认；
- 是否自动淘汰；
- 是否可导出申请材料。

### 5.4 决策依据

每个 `DecisionTrace` 至少包含：

- 观察到的 JobRequirement 和来源；
- 使用的 Claim/Evidence/Observation refs；
- 命中的规则；
- 结构化 findings；
- 替代解释，例如“简历未出现不等于没有做过”；
- uncertainties；
- 下一步动作；
- `human_review_required` 候选人端默认为 false，但 `unknown/constraint conflict` 可为 true。

---

## 6. API 契约

新增路由文件：`backend/app/opportunity_workflow_routes.py`，统一前缀 `/opportunity-workflows`，在 `main.py` 注册。

所有写接口要求候选人权限与 `Idempotency-Key`。

### 6.1 创建工作流

`POST /opportunity-workflows`

请求：

```json
{
  "resume_id": "uuid",
  "entry_mode": "target",
  "target_job_id": "uuid"
}
```

Explore 模式允许 `target_job_id=null`。

响应至少包括 workflow、下一步 `select_target/build_routes` 和背景完整性摘要。

### 6.1A 导入外部真实 JD

`POST /opportunity-workflows/targets:import`

第一版必须支持直接粘贴 JD 文本；职位 URL 仅作为来源引用保存，不由后端主动抓取，避免 SSRF、登录态、服务条款和来源真实性问题。

请求：

```json
{
  "title": "AI 应用工程师",
  "company_name": "用户填写或从正文确认",
  "jd_text": "完整 JD 文本",
  "source_url": "https://example.com/jobs/123",
  "source_platform": "company_site"
}
```

要求：

- 创建仅该候选人可访问的私有岗位记录和不可变 JD 原文快照；
- AI/规则提取 5–8 项要求后，必须让用户确认或修改再进入路由；
- 保存正文哈希、创建时间、用户确认状态和可空来源 URL；
- 不得把用户粘贴的 JD 自动公开到岗位列表；
- 不得把 JD 内容当作候选人事实；
- 同一用户、相同正文哈希的重复导入保持幂等；
- 首发验证只接受中国大陆的互联网/AI 首发岗位族；其他岗位允许保存草稿，但明确显示“尚未纳入本轮校准范围”。

响应返回可用于 `target_job_id` 的私有岗位 ID、要求提取状态和下一步 `confirm_requirements`。

实现约束：本端点复用 `POST /advisor/target-jobs/import` 的解析与建表逻辑（按需抽为共享函数），不得新写第二套 JD 解析器；同时必须提供 owner 可见的私有岗位读取路径，否则用户导入后在目标选择器里看不到自己的 JD（见 2.4）。

### 6.1B 确认要求

`POST /opportunity-workflows/targets/{job_id}/requirements:confirm`

用户可以增删改抽取出的要求，并标记哪几项是自己最在意的。要求确认前 `routes:build` 必须返回 409，避免在错误的要求集合上路由。

请求至少包含：保留的要求 ID 列表、用户新增的要求文本、被删除的要求 ID。响应返回最终要求集合与 `requirements_confirmation_state='confirmed'`。

必须记录：抽取版本、用户删除数、用户新增数和用户修改数。这三个计数是 R3-06 的要求抽取质量指标来源，不得只保存最终结果。

### 6.2 获取轻量方向

`GET /opportunity-workflows/directions?resume_id={id}`

固定返回三个 lane：

- `current`：当前证据覆盖较高；
- `adjacent`：有可迁移证据；
- `stretch`：存在明确发展空间。

每个 lane 返回：角色族、解释、使用的 Claim refs、2–5 个当前数据库中的真实岗位示例。不得返回“市场前景最好”“录用概率最高”等未经数据支持的结论。

第三轮的方向 lane 只允许落在 1.0 定义的四个首发岗位族中，并标注“基于当前个人证据的探索建议，不代表实时市场需求”。Explore 不得阻塞 Target 主流程或成为首轮商业成功的必要条件。

### 6.3 选择目标

`POST /opportunity-workflows/{workflow_id}/target`

```json
{
  "target_job_id": "uuid",
  "direction_lane": "adjacent"
}
```

保存不可变 direction snapshot；目标变化需在尚未 route 时允许，route 后改目标必须新建工作流。

`target_job_id` 可以指向平台公开岗位或 6.1A 创建的候选人私有岗位；所有读取、要求确认和路由接口必须验证相应可见性。

### 6.4 生成/刷新路由

`POST /opportunity-workflows/{workflow_id}/routes:build`

响应：

```json
{
  "workflow": {"id": "...", "status": "clarifying"},
  "summary": {
    "supported": 3,
    "clarify": 2,
    "develop": 0,
    "constraint": 1,
    "unknown": 1
  },
  "routes": [
    {
      "id": "...",
      "requirement": {"id": "...", "text": "...", "importance": 90},
      "state": "clarify",
      "summary": "你可能有相关经历，但个人责任还不清楚。",
      "missing_fields": ["candidate_action"],
      "source_refs": [],
      "next_action": {"type": "answer_question"}
    }
  ]
}
```

重复相同输入应幂等；输入快照变化时追加事件并更新当前路由。

### 6.5 获取工作流

- `GET /opportunity-workflows/{workflow_id}`；
- `GET /opportunity-workflows/{workflow_id}/routes`；
- `GET /opportunity-workflows?status=active&limit=20`。

他人 workflow 统一返回 404，避免枚举。

### 6.6 启动澄清

`POST /opportunity-workflows/{workflow_id}/clarification-session`

请求可选 `route_ids`，服务端最多选 3 个。复用 `InterviewSession(mode='target_gap')`，每个问题绑定 `requirement_route_id`。

回答、观察确认继续复用：

- `POST /interview-sessions/{session_id}/answers`；
- `POST /interview-observations/{observation_id}/confirm`；
- `POST /interview-observations/{observation_id}/reject`。

观察确认后，调用：

`POST /opportunity-workflows/{workflow_id}/routes:recompute`

只重算受影响 route，并追加状态事件。

用户选择“我目前没有相关经历”必须是显式字段，例如：

```json
{
  "question_id": "...",
  "user_declined": true,
  "decline_reason": "no_relevant_experience"
}
```

需要将 `no_relevant_experience` 加入允许的 decline reason；它与 `skip_for_now`、`stop_followup` 语义不同。

### 6.7 创建发展任务

`POST /opportunity-workflows/{workflow_id}/routes/{route_id}/development-action`

前置条件：当前 route 必须为 `develop`，并存在用户明确确认事件。

返回复用的 `ReadinessAction`。同一路由存在 planned/in_progress action 时幂等返回，不重复创建。

### 6.8 生成部分申请包

`POST /opportunity-workflows/{workflow_id}/application-packages`

只读取 `supported` 路由及其已确认来源。生成失败必须指出被 Fidelity 门禁阻断的 item，不得自动补全。

- `GET /opportunity-workflows/{workflow_id}/application-packages/latest`；
- `POST /application-packages/{draft_id}/export`。

第一版 export 可以返回结构化 JSON/纯文本下载，不要求新增 PDF/DOCX。

### 6.9 用户反馈

`POST /opportunity-workflows/{workflow_id}/routes/{route_id}/feedback`

```json
{
  "accurate": true,
  "useful": true,
  "expected_state": null,
  "comment": "问题能让我想起相关项目"
}
```

反馈属于评测数据，不能直接修改 route 真相；状态修正必须走明确操作和事件。

---

## 7. 匹配算法 V4 的最小改造

### 7.1 新定位

`matching_hybrid.py` 继续负责岗位召回和旧基线，不负责判断候选人有没有能力。新工作流以 JobRequirement 为单位运行路由。

### 7.2 Target 与 Explore 模式

在内部匹配入口增加 `match_mode: Literal['target','explore']`：

- `target`：用户已经选择岗位，不使用候选人历史职位 gate 排除该岗位；
- `explore`：输出 current/adjacent/stretch 三 lane，不将 adjacent 直接过滤；
- 旧接口未传参数时保持兼容，但 UI 不再用旧总分作为核心结论。

### 7.3 P0 删除或隔离

修改：

- `backend/app/matching_signals.py`：删除 `PRESTIGE_COMPANIES` 补偿；停止返回 `probabilities`；
- `backend/app/matching_rerank.py`：从 `_profile_summary` 删除 `name`，增加匿名 Claim/Experience/confirmation 摘要；
- `backend/app/matching_preference.py`：Explore 模式允许 adjacent/stretch；
- `backend/app/matching_hybrid.py`：将补充信号标记为 display/context only，不供五状态判断；
- 前端 `MatchEvaluationPanel.jsx`、`TopJobMatches.jsx`：删除概率和潜力真相表达，改成“召回参考”和证据覆盖提示。

兼容要求：如果旧客户端仍读取字段，可以先返回 `null` 并添加 deprecation metadata，一个工作包后删除；不得继续返回伪概率数字。

### 7.4 V4 不做的事

- 不训练排序模型；
- 不用用户结果回写直接在线更新权重；
- 不把学校、公司品牌、年龄、性别、民族等加入路由；
- 不把 LLM adjustment 当作真相；
- 不声称相邻岗位推荐代表真实市场需求。

---

## 8. 前端信息架构与组件

保留 URL `/candidate/advisor`，将 `frontend/src/pages/Candidate/Advisor.jsx` 改为第三轮工作台壳。原四层岗位画像和 Advisor Chat 收入“岗位信息与顾问”折叠区，不占据第一屏主任务。

### 8.1 页面阶段

1. `background`：选择 Resume，显示 Career Passport 完整性，提供导入入口；
2. `entry`：选择“我有目标岗位”或“帮我探索方向”；
3. `target`：默认展示 JD 粘贴框，次要位置提供平台岗位库选择；粘贴后进入要求确认，用户可增删改后再路由；
4. `routing`：展示要求证据地图；
5. `clarifying`：最多三个问题；
6. `package`：当前可用申请包；
7. `actions`：长期发展任务与结果记录。

刷新页面后必须由后端 workflow status 恢复阶段，不把核心状态只保存在 React state。

### 8.2 新组件建议

目录：`frontend/src/components/opportunity/`

- `WorkflowEntrySelector.jsx`；
- `DirectionLaneSelector.jsx`（Explore 次要路径，可在 flag 后）；
- `TargetJobSelector.jsx`：默认 tab 为“粘贴 JD”，次要 tab 为“平台岗位库”，不得把下拉选择做成唯一入口；
- `RequirementConfirmList.jsx`：抽取结果的增删改与重点标记，对应 6.1B；
- `RequirementRouteBoard.jsx`；
- `RequirementRouteCard.jsx`；
- `ClarificationDrawer.jsx`；
- `CurrentApplicationPackage.jsx`；
- `DevelopmentActionCard.jsx`；
- `WorkflowProgressHeader.jsx`；
- `RouteSourceDrawer.jsx`。

### 8.3 状态文案

| 机器状态 | UI 文案 | 禁止文案 |
|---|---|---|
| supported | 已有证据支持 | 你一定具备 |
| clarify | 可能做过，需要说清楚 | 表达能力差 |
| develop | 目前还没有足够证据，可通过行动补齐 | 你不具备/不合格 |
| constraint | 现实条件需要确认 | 硬伤/淘汰 |
| unknown | 暂时无法可靠判断 | 系统判断失败 |

### 8.4 第一屏必须回答三个问题

- 我已经有什么？
- 哪些只需要说清楚？
- 下一步只需要做什么？

不得首先展示一个大号总分、概率或“击败多少候选人”。

### 8.5 兼容页面

- `MyResumes.jsx` 中旧 `TargetJobOptimizationPanel` 暂时保留，并增加“在岗位工作台继续”入口；
- `JobList.jsx` 和 `BrowseJobs.jsx` 增加“用这个岗位开始分析”，创建 target workflow 后跳转 Advisor；这是次要入口，不能替代粘贴 JD；
- 目标岗位选择器不得只依赖 `GET /browse-jobs`：该接口会过滤掉用户自己导入的私有 JD（见 2.4），必须同时读取本人私有岗位；
- `CareerPassport.jsx`、`EvidenceVault.jsx` 负责深度编辑，工作台只显示摘要和链接；
- `AppliedJobs.jsx` 继续负责正式投递状态，不复制申请状态机。

---

## 9. 工作包拆分

## R3-00：契约、测试骨架与只读基线

目标：不改变生产行为，固定五状态、API Schema、旧算法基线和安全门禁。

新增/修改：

- 新建 `backend/app/opportunity_routing_schemas.py`；
- 新建 `backend/tests/test_r3_routing_contract.py`；
- 新建 `backend/tests/fixtures/r3_routing_cases.json`，仅放匿名合成/获授权案例；
- 新建 `frontend/src/components/opportunity/routeState.js`；
- 新建对应 Node contract test；
- 记录旧匹配输出，不改权重。

必须测试：

- 五状态枚举与中文文案；
- 初始无证据不允许 develop；
- supported 必须有来源；
- unknown 可以合法返回；
- 约束状态不计入能力覆盖；
- 事实编造关键字/新增事实检测；
- 旧 PR11–PR15 测试仍通过。

完成门禁：测试先证明旧实现缺少路由契约，但不能通过修改旧业务假装实现完成。

## R3-01：数据库、Workflow CRUD 与 JD 导入

目标：落地 4.1～4.5A 模型、迁移、权限、幂等和基础 CRUD，并打通 6.1A/6.1B 的粘贴 JD 与要求确认。规则解析即可，不接 AI。

文件：

- `backend/app/models_db.py`；
- 新 Alembic revision，`down_revision='pr15_screening'`；
- `backend/scripts/migrations/20260803_r3_opportunity_workflow_up.sql`；
- 对应 down SQL；
- `backend/app/opportunity_workflow_routes.py`；
- `backend/app/advisor_routes.py` 或共享导入模块：抽出 JD 导入逻辑供两个路由复用，不新写解析器；
- `backend/app/main.py`；
- `backend/tests/test_r3_opportunity_workflow.py`；
- `backend/tests/test_r3_target_job_import.py`；
- `backend/tests/test_migration_sql_unit.py`。

测试：所有权、404 防枚举、幂等重放/冲突、非法状态、目标更换限制、up/down/up、PostgreSQL 并发创建。

JD 导入必须测试：

- 粘贴外部 JD 后，本人能在目标选择器数据源里读到该私有岗位；
- 候选人 B 读取候选人 A 的私有岗位返回 404；
- 私有岗位不出现在 `/browse-jobs` 公开列表；
- 同一用户相同 `jd_text_hash` 重复导入幂等，不产生第二条岗位；
- `requirements_confirmation_state='pending'` 时 `routes:build` 返回 409；
- 6.1B 记录用户的删除/新增/修改计数；
- `source_url` 只保存不抓取，后端不发起出站请求；
- 首发范围外的岗位可保存但标记 `out_of_scope`。

## R3-02：证据检索、路由器与匹配 V4 安全修正

目标：实现规则优先的初始路由和 DecisionTrace；完成第 7 节 P0 修正。

文件：

- 新建 `opportunity_evidence_router.py`；
- 修改 `career_vault.py` 增加按 requirement 检索的只读 helper；
- 修改 `matching_signals.py`、`matching_preference.py`、`matching_hybrid.py`、`matching_rerank.py`；
- 新建 `test_r3_opportunity_evidence_router.py`；
- 扩展 `test_matching_human_preferences.py`、`test_fairness_baseline.py`。

必须测试：

- 空简历 → clarify/unknown，不是 develop；
- 已确认 Claim → supported；
- 未确认模型 observation → 不能 supported；
- 证据冲突 → unknown；
- objective constraint 独立；
- 撤回 Evidence 后 supported 降级并有事件；
- 名企名称不提高行业覆盖；
- API 不返回面试/Offer 概率；
- rerank 输入不含姓名；
- Explore 返回 adjacent lane。

要求抽取质量（首发岗位族各准备至少 5 份真实 JD 的匿名样本）：

- 每份 JD 抽出 5–8 项要求，不得少于 3 项或多于 12 项；
- 能力要求与客观约束被正确分开；
- 抽取结果不含公司宣传语、福利和薪酬条款；
- 同一份 JD 重复抽取结果稳定；
- 纯规则路径（AI 关闭）也能产出可确认的要求集合，允许质量下降但不得为空。

## R3-03：最多三问、状态重算与发展任务

目标：复用 InterviewSession 完成 clarify 闭环，复用 ReadinessAction 完成 develop 闭环。

文件：

- 扩展模型和 R3 migration 或创建后续 migration；
- 修改 `interview_sessions.py`、`interview_policy.py`、`interview_session_routes.py`；
- 修改 `personalized_guidance.py`；
- 扩展 `opportunity_workflow_routes.py`；
- 新建 `test_r3_clarification_routing.py`；
- 扩展 `test_pr12_interview_sessions.py`、`test_personalized_guidance.py`。

必须测试：

- 首轮最多 3 问；
- 问题绑定 route/requirement；
- `no_relevant_experience` 才允许 clarify→develop；
- `skip_for_now` 进入 unknown；
- 观察未确认不改变 route；
- 观察确认后只重算相关 route；
- develop action 不重复创建；
- 任务 completed 无证据时不进入 supported；
- revoke consent 后不能写回。

## R3-04：当前可用申请包

目标：只用 supported 来源生成可审计的部分材料。

文件：

- 新增 Draft/Item 模型与 migration；
- 新建 `backend/app/application_package.py`；
- 扩展 workflow routes；
- 复用 `fidelity_proof.py`、`resume_variants.py` 中安全部分；
- 新建 `test_r3_partial_application_package.py`。

必须测试：

- 只有 supported 项进入可导出材料；
- JD 文本不能被写成候选人事实；
- clarify/develop/unknown 只成为内部 note；
- 任一新增事实使 item blocked；
- withdrawn Evidence 使旧 draft superseded；
- export 保存不可变快照；
- 重试幂等。

计费挂钩点：R3-06 的商业门禁要测“¥39–59 解锁多 JD / 完整申请包”，因此导出接口必须预留一个具名 feature key（复用 `usage_metering.py` 的 `reserve_feature_entitlement` 语义），本轮默认放行且 `METERING_ENABLED` 关闭时不生效。本轮不接支付收单；试点收费走人工收款或可退押金。若决定本轮完全人工放行，也必须在实施报告中显式写明，不得留下“将来再说”的空白。

## R3-05：候选人统一工作台

目标：完成第 8 节页面，替换 Advisor 第一屏任务，但保留旧功能入口。

文件：

- 重构 `frontend/src/pages/Candidate/Advisor.jsx`；
- 新增 `frontend/src/components/opportunity/*`；
- 修改 `frontend/src/api/index.js`（若项目仍统一使用 Axios 实例，只增加语义封装，不重复客户端）；
- 修改 `BrowseJobs.jsx`、`JobList.jsx`、`MyResumes.jsx`；
- 修改 `styles/app.css`；
- 新增 Node copy/contract tests；
- 新增 `frontend/e2e/r3-opportunity-workflow.spec.js`。

E2E 必须覆盖：

1. 导入已有 Resume；
2. Target 模式粘贴一份外部真实 JD，确认 5–8 项要求；
3. 看到五状态卡片；
4. 回答问题并确认 observation；
5. 路由即时变化；
6. 在仍有缺口时生成部分申请包；
7. 刷新后恢复 workflow；
8. AI 关闭后的规则路径；
9. 移动端宽度下主流程可完成。

另以独立用例验证平台已有岗位仍可直接创建 Target workflow，且候选人 A 无法访问候选人 B 导入的私有 JD。

Explore 模式选择 adjacent 方向作为**非阻塞**用例：失败时记录并单独修复，不阻断 R3-05 门禁。依据 1.0，Explore 本轮是次要路径；工程时间冲突时优先保证粘贴 JD 到申请包这条主链路。

## R3-06：产品质量评测、商业试点和发布决策

目标：同时建立产品质量门禁和真实商业门禁；不把合成数据、主观好评、注册量或一次性使用包装成市场验证。

**试点时序：** 商业试点不等 R3-06 全部脚本就绪。R3-03 打通澄清闭环后即可用人工陪跑开始招募前 5 名用户，R3-05 上线后转为自助。等到全部工程门禁跑完再开始招募，四周内拿不到付款和七日复访数据。

### 三个对照组

三组必须都跑，报告必须分别列出，不得互相替代：

| 组 | 定义 | 回答的问题 |
|---|---|---|
| A：QLink 旧基线 | 当前匹配算法：关键词/固定权重、总分与笼统缺口、通用追问 | 新机制相对自家旧版有没有进步 |
| B：新路由 | 本轮五状态路由、最多三问、部分申请包 | 待验证方案本身 |
| C：通用大模型基线 | 把同一份简历与同一份 JD 直接交给通用大模型（ChatGPT / DeepSeek），使用一个固定的、公平的分析提示词 | 用户真正会问的“我为什么不用免费的通用 AI” |

B 对 A 的提升进入产品质量门禁；**B 对 C 的提升进入商业门禁，并且是本轮是否继续的决定性证据**。只赢 A 不赢 C 时，结论只能是 `Iterate` 或 `Stop`。C 组提示词、模型版本和日期必须存档，评分者对组别应尽量盲评。

新增：

- `backend/scripts/r3_evaluate_routing.py`；
- `backend/tests/fixtures/r3_routing_cases.schema.json`；
- `R3_LABELING_GUIDE.md`；
- `R3_PILOT_PROTOCOL.md`；
- 产品质量评测报告模板；
- 商业试点招募、收费、七日复访和 Go/Iterate/Stop 报告模板。

计算：

- confusion matrix；
- Macro-F1；
- false-supported rate；
- false-develop rate；
- clarification resolution rate；
- abstention/unknown rate；
- 问题可回答率；
- B 对 A、B 对 C 两组下一步有用率差；
- 要求抽取的用户修改率（6.1B 记录的删除/新增/修改计数 ÷ 抽取总数）；
- time-to-first-useful-output；
- fact hallucination rate。

产品质量门禁：

- Macro-F1 ≥ 0.75；
- false-supported ≤ 5%；
- false-develop ≤ 10%；
- clarification resolution ≥ 60%；
- 问题可回答率 ≥ 80%；
- 用户准确/有用反馈 ≥ 80%；
- B 比 A 的下一步有用率提升 ≥ 15 个百分点；
- 要求抽取的用户修改率 ≤ 30%，且没有用户把整份抽取结果推翻重填；
- fact hallucination = 0；
- 首次有用产出中位数 ≤ 5 分钟。

30–50 条只作为预实验；正式发布门禁需要 60–100 个“岗位要求 × 候选人背景”案例，并由候选人确认事实、招聘/领域评审判断证据充分性。

商业试点必须满足：

- 招募 20–30 名符合 1.0 定义的真实用户，不以“对 AI 感兴趣”作为入组条件；
- 每名用户带入一份正在考虑申请的中国互联网/AI 真实 JD 和至少两段经历；
- 随机或交叉安排 C 组：用固定提示词把同一份简历和 JD 交给通用大模型，产出与 B 组并排给用户盲评；
- 记录首轮完成、具体行动改变、申请包采用、7 日第二次有效行为和真实付款；
- 测试一次免费体验后 ¥39 与 ¥59 两个价格点；可补充测试 ¥99–199 的三个月求职季方案，但不得用“口头愿意购买”代替付款；
- 付款可使用人工收款或规则明确的可退押金，不要求本轮建设正式支付系统；
- 招募、访谈和付款数据必须去标识化保存，用户可撤回，支付凭证不得进入普通产品埋点。

商业门禁：

- ≥ 70% 的用户能说出一个被产品改变的具体下一步；
- ≥ 50% 在 7 天内完成第二次有效行为；
- ≥ 5 名用户真实支付 ¥39–59 或同额可退押金；
- B 组相对 C 组通用大模型基线的“下一步有用率”提升 ≥ 15 个百分点；这条不通过时，其余商业指标全部通过也不能判 `Go`；
- 至少 30% 的试点用户把生成的一个申请包项目用于真实申请准备；
- 获客来源、人工支持时间和单用户模型成本均有记录，即使样本量暂不足以计算稳定 CAC/LTV。

发布决策：

1. **Go**：产品质量和商业门禁全部通过，扩大同一地区与岗位族的受控试点；
2. **Iterate**：质量通过但商业门禁未通过，或价值集中在某一个岗位族；保持范围或进一步收窄，不扩大功能；
3. **Stop / Pivot**：相对通用大模型没有显著价值提升，或用户没有第二次行为和真实付款；停止把岗位证据路由作为主卖点。

---

## 10. 埋点与可观测性

第三轮事件不得滥用计费 `UsageEvent` 作为唯一分析表。路由审计写 `RequirementRouteEvent`；产品漏斗可先使用结构化应用日志或新增受控 workflow event 表。

事件名：

- `workflow_started`；
- `target_jd_imported/requirements_confirmed`；
- `entry_mode_selected`；
- `direction_viewed/selected`；
- `target_selected`；
- `requirement_extracted`；
- `evidence_retrieved`；
- `requirement_routed`；
- `clarification_asked/answered/resolved`；
- `evidence_confirmed/withdrawn`；
- `development_task_created/completed`；
- `partial_pack_generated/exported`；
- `route_feedback_submitted`；
- `pilot_price_offered/pilot_payment_committed`；
- `second_value_action_completed`；
- `outcome_recorded`。

不得记录：

- 原始完整简历到普通应用日志；
- 原始回答正文到埋点 payload；
- access token、身份证件、电话、邮箱；
- 支付账号、银行卡、交易凭证正文；
- 模型隐藏思维链。

每次 AI 调用继续写 `AIInvocation`，包含 task、模型、Prompt/Schema、input hash、耗时、状态和成本，不存原始敏感正文。

---

## 11. 测试与执行命令门禁

Cursor 先依据当前环境确认可用命令，不得伪造测试结果。

### 后端

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
.venv/bin/mypy app
```

若仓库没有 `.venv`，必须报告缺少运行环境；得到授权后再安装依赖。不得改用开发数据库强行运行。

PostgreSQL 专项：

```bash
TEST_DATABASE_URL='postgresql+asyncpg://.../jobplatform_test' \
.venv/bin/python -m pytest -q -m postgresql tests/test_r3_postgres_concurrency.py
```

### 前端

```bash
cd frontend
npm test
npm run lint
npm run build
npm run e2e -- r3-opportunity-workflow.spec.js
```

### 迁移

- 在隔离 PostgreSQL 上执行 up → down → up；
- 验证 `scripts.migrate` 与 Alembic revision 状态；
- 验证 SQLite 默认测试不因 PostgreSQL 专属 DDL 失败；
- downgrade 不得删除第三轮之前的数据；
- 生产 worker 仍只能校验 schema，不自动迁移。

### 每包固定回归

- 当前工作包定向测试；
- PR11 Career Vault；
- PR12 Interview Sessions；
- PR13 Target Optimization；
- PR14 Advisor；
- PR15 Screening；
- Fairness、安全和 Fidelity 测试；
- 前端 test/lint/build。

---

## 12. 人工验收脚本

使用 candidate A：

1. 打开 `/candidate/advisor`；
2. 选择一份已导入 Career Passport 的简历；
3. 选择 Target 模式，粘贴一份平台岗位库里没有的外部真实 JD；
4. 确认显示 5–8 项关键要求，删掉一项、补一项，再确认；
4A. 返回目标选择器，确认刚导入的 JD 仍能被自己找到并复用；
5. 检查每项状态、解释、来源和下一步；
6. 确认无证据项没有直接显示“能力不足”；
7. 回答一个 clarify 问题但暂不确认 observation，状态不应变化；
8. 确认 observation 后重算，相关 route 应变化；
9. 对另一个问题选择“目前没有相关经历”，出现一个 develop action；
10. 在仍有未解决项时生成当前申请包；
11. 检查导出内容只包含已确认事实；
12. 刷新页面，流程状态恢复；
13. 撤回一个 Evidence，原 supported route 降级并留下事件；
14. 关闭 AI，确认手动/规则路径仍可用。

使用 candidate B 验证不能访问 candidate A 的 workflow、route、session、package 和导入的私有 JD。

使用 employer A 验证现有 Screening 不受影响，且系统没有自动改变申请终态。

---

## 13. 回滚与兼容策略

1. 新工作流由后端 feature flag `OPPORTUNITY_WORKFLOW_V1_ENABLED` 控制；默认开发开启，生产需显式开启。
2. 前端 flag 关闭时继续显示现有 Advisor 页面。
3. 每个 migration 有 down SQL；不得让 downgrade 删除旧 PR11–PR15 表或字段。
4. 旧 Target Job Optimization API 保留至少一个完整发布周期。
5. 旧总分字段先 deprecate，再删除；伪概率字段必须停止生成，可以短期返回 null。
6. 新路由失败时返回可恢复错误和已有工作流状态，不把数据库置于半完成状态。
7. Package 生成失败不影响 route 和 Claim；事务边界独立。

---

## 14. Cursor 每次工作包的标准提示模板

用户可以把下面模板复制给 Cursor，并将 `{WORK_PACKAGE}` 换成 R3-00～R3-06：

```text
请实施 CURSOR_THIRD_ROUND_IMPLEMENTATION_SPEC.md 中的 {WORK_PACKAGE}，不要实施其他工作包。

开始前：
1. 完整阅读第三轮规格、NEXT_ITERATION_EXECUTABLE_PRODUCT_PLAN.md、第二轮 INV-01～INV-10 和 CURSOR_DEFINITION_OF_DONE.md。
2. 检查 git status，保护所有现有改动。
3. 先做只读差距审计，输出需求追踪矩阵、涉及文件、迁移、风险和测试计划。
4. 先补失败测试，再实施。

实施时：
- 复用现有 JobRequirement、ResumeClaim、EvidenceArtifact、InterviewSession、ReadinessAction、ResumePatchProposal 和 DecisionTrace；
- JD 导入复用 advisor_routes 既有实现，不新写第二套解析器或私有岗位表；
- 主入口是用户粘贴自己的 JD，平台岗位库是次要路径；
- 不建立平行系统；
- 无证据不得判断能力不足；
- 未确认事实不得写入申请材料；
- 所有后端资源必须校验归属；
- 所有状态变化必须追加审计事件；
- 不修改无关文件。

完成后报告：
1. 修改文件与原因；
2. 行为和 API 变化；
3. migration up/down；
4. 新增测试；
5. 实际执行命令、退出码和结果；
6. 人工验收步骤；
7. 未解决风险；
8. 是否达到该工作包门禁；
9. 确认未覆盖任务开始前的用户改动。
```

---

## 15. 第三轮最终 Definition of Done

只有同时满足以下条件，第三轮才算完成：

- R3-00～R3-06 分包完成并有独立报告；
- 新工作流不是只存在于前端，本地刷新可恢复；
- 每项岗位要求都有可审计状态与来源；
- 初始无证据不会进入 develop；
- supported 均有确认来源；
- develop 必须有用户明确确认；
- 部分申请包事实编造率为零；
- 旧 PR11～PR15 主流程无回归；
- Candidate A/B 跨用户访问全部失败；
- AI 关闭路径可用；
- up/down/up migration 通过；
- 后端、前端、E2E 和公平性门禁有真实执行证据；
- 预实验质量指标有报告，且没有被包装成正式市场验证；
- 用户可以粘贴一份平台库中没有的外部 JD 走完全流程，并能再次找到自己导入的 JD；
- 20–30 名中国互联网/AI 首发 ICP 用户的真实 JD 试点已经完成；
- 具体行动改变率、7 日第二次有效行为率、申请包真实采用率和付款人数均有报告；
- 已与通用大模型基线比较，而不是只与旧版 QLink 比较；
- 产品质量门禁和商业门禁分别给出通过/未通过结论，不得相互替代；
- 团队作出 Go / Iterate / Stop 决策；
- 主流程稳定后再进入 PR16/PR17，而不是以第三轮替代合规和正式发布评测。

第三轮的目标不是完成更多页面，而是证明 QLink 能稳定避免两个关键错误：把“没写清楚”当成“不会”，以及把“没有证据”当成“已经具备”；并证明中国互联网/AI 首发用户会因此改变下一步、再次回来、采用申请材料并真实付费。

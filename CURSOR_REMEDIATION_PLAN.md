# AI Job Platform 整改与增强任务书（供 Cursor 执行）

## 0. 使用方式

这是一份实施任务书，不要求一次性完成全部内容。Cursor 应按下方阶段顺序工作，每个阶段单独提交、单独测试，禁止在一个大改动中同时重构权限、数据库、AI 评分和 UI。

执行前必须先：

1. 阅读整个仓库和当前 `git status`，保留所有已有未提交改动，不覆盖、不回滚用户代码。
2. 建立当前行为基线，记录可以运行的页面、接口和测试。
3. 每次只实现一个阶段或一个明确任务；修改前说明涉及文件、数据迁移和兼容风险。
4. 所有后端权限必须由服务端校验，不能依赖 `localStorage`、前端路由或前端传入的 `user_id` / `employer_id`。
5. AI 不得编造候选人没有提供的经历、数字、证书、技能或结果。
6. 所有新功能必须包含测试、错误态、空状态、加载态和最小文档。

当前只要求 Cursor 按此文档修改；不要删除现有产品能力。

涉及公开数据、可信度审计、AI 面试、简历写回和岗位推荐时，还必须阅读 `AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`，但不得把其中全部 Phase 混入当前安全整改 PR。

所有批次必须遵守 `CURSOR_DEFINITION_OF_DONE.md`。当前收口还必须阅读 `CURSOR_PR0_PR3_CLOSURE_SPEC.md`，PR3 必须完整阅读 `PR3_IMPLEMENTATION_SPEC.md`；后者细化 PR3 的实现路径，前者定义 PR0–PR3 安全阻断范围。

### 当前进度与研究校准（2026-07-23）

- PR 0 已建立测试数据库隔离、权限 fixture 与 Findings 回归骨架，但收口规格要求继续补强真实权限矩阵、数据库隔离和 SSE 可达性验证；
- PR 1 原定向回归已通过，但“招聘方自动创建申请后获得审计权限”的授权链风险重新打开，需按收口规格关闭；
- PR 2 三个原定向测试均通过；完整后端测试曾为 `39 passed, 1 xfailed`，但服务端 evidence 真相源仍需按收口规格补齐；
- 前端 production build 已通过；全局 lint 仍有 25 个 errors、14 个 warnings，纳入 PR 5.5/PR 7 收敛；
- PR 3 已有部分实现，但尚未完成语义、迁移、并发和完整验收；当前执行 PR0–PR3 收口，不并行展开后续功能；
- 2026-07-24 现有后端套件为 `49 passed`，但其中包含错误的“人工关闭后 clarified”契约，不能据此宣布收口完成；
- 文献评估支持“安全优先、忠实写回、可解释反事实、Claim 溯源”的总体方向；
- 实施顺序调整为 **先 Claim Passport，后完整版 Potential Score**；
- Claim Passport 只表达来源与处理历史，不表达绝对真实性认证；
- Potential Score 对外优先称“可提升空间模拟”，只表示当前模型内变化，不表示录用概率；
- “增强简历竞争力”不得再把补充数字作为默认答案；PR 9 必须先识别表达、相关性、证据、能力和硬门槛缺口，再提供多条可选择的优化路径；
- “大公司偏好画像”对外和数据模型中逐步收敛为“目标岗位能力画像 + 公司工作语境画像 + 证据偏好画像”，不得用历史员工人口属性反推录用偏好；
- 试点前必须补充 delta 校准、虚假补救用例和最低公平性监控。

---

## 1. 产品目标与当前定位

项目当前是“功能较完整的内部 Alpha / 商业验证原型”，已有：

- 候选人和招聘方双端；
- 简历上传、解析、体检、建议、定制版本；
- 岗位发布、浏览、匹配和投递；
- Claim 级澄清、可信度审计、面试邀请和虚拟面试；
- 公司画像、录用画像、配额与粗略成本记录。

本轮整改目标不是继续堆零散功能，而是达到：

1. 客户无需分别启动前端、后端、数据库和 Redis；
2. 所有真实数据受到服务端权限和隐私保护；
3. `potential_score` 从一个分数升级成可解释的反事实求职模拟；
4. 增加 Claim Passport，使简历主张、证据、改写、澄清和审计可追溯；
5. 建立测试、迁移、监控和部署基础，使项目能够小范围真实试点。

---

## 2. P0：客户启动与交付体验

### 2.1 先明确交付方式

优先级从高到低：

1. **正式客户：托管成 Web SaaS。** 客户只打开一个 HTTPS 地址，不应在客户电脑上运行前后端。
2. **私有化客户：单条 Docker Compose 命令。** 客户只执行 `docker compose up -d --build`，不再分别运行 npm、uvicorn、PostgreSQL 和 Redis。
3. **移动访问：先做响应式 Web/PWA。** 支持添加到主屏幕和 Web Push；不在核心 Web 流程稳定前开发完整原生 App。
4. **开发人员：根目录统一命令。** 提供 `make dev` / `make test` / `make stop` 或跨平台等价脚本。

不要把“让非技术客户运行两个终端”当作最终解决方案。

App Store 客户端属于后续阶段，只在移动端高频场景得到验证后启动，例如面试邀请通知、澄清回复、面试练习和进度提醒。招聘方的岗位管理、候选人对比、可信度审计，以及候选人的简历编辑仍以 Web 为主。禁止只把网站包进 WebView 提交商店。

### 2.2 Docker Compose 一键启动

修改现有 Compose，使其至少包含：

- `frontend`：多阶段构建 React，使用 Nginx 或等价静态服务；
- `backend`：生产模式启动，不使用 `--reload`；
- `db`：PostgreSQL + pgvector；
- `redis`；
- 可选 `worker` / `scheduler`：承载抓取、匹配、分析重建等后台任务；
- 所有服务健康检查和合理的启动依赖；
- 持久化卷；
- 后端不直接暴露给最终客户，由统一入口反向代理 `/api` 和 `/ws`；
- 浏览器只访问一个端口或域名，避免 CORS 和多个地址配置。

验收标准：

- 新环境仅安装 Docker 后，一条命令可以启动完整平台；
- 打开一个 URL 可以注册、登录、上传简历、浏览岗位；
- 前端不再默认写死 `http://localhost:8000`；
- `docker compose ps` 中核心服务均为 healthy；
- 重启容器后数据库数据仍存在；
- 停止和升级步骤写入根目录 README。

### 2.3 环境变量与首次启动

新增安全的 `.env.example`，只提供字段和说明，不包含真实密钥。至少包含：

- 数据库、Redis；
- JWT 密钥；
- 模型 API 地址、模型名和 Key；
- CORS / 公网地址；
- SMTP；
- 配额开关；
- 数据抓取开关；
- 环境类型。

启动时增加配置校验：生产环境缺少关键配置应明确失败，错误信息不得泄露密钥。

如果模型 Key 缺失，系统应进入“本地规则降级模式”，并在管理页或健康检查中明确显示哪些 AI 功能不可用，而不是页面无提示失败。

### 2.4 客户友好的首次使用体验

增加：

- 首次进入向导：选择候选人/招聘方、上传示例或跳过；
- 空数据库时可选加载脱敏演示数据；
- `/health` 只返回适合公开展示的状态；另设受保护的详细 readiness 检查；
- README 提供“3 分钟启动”“升级”“备份”“恢复”“常见错误”。

---

## 3. P0：安全、权限和隐私阻断项

### 3.1 统一服务端鉴权

审计全部 FastAPI 路由，给每个非公开接口补齐：

- 登录认证；
- 角色校验；
- 资源归属校验；
- 输入校验；
- 必要的限流和配额。

重点检查现有旧接口：

- `/post-job`：不能接收或信任任意 `employer_id`，必须使用当前登录招聘方 ID；
- `/jobs/{employer_id}`：只能查询本人岗位或改成 `/jobs/mine`；
- `PUT/DELETE /jobs/{job_id}`：必须校验岗位属于当前招聘方；
- `/match`、`/match/user/{user_id}`、`/matches/user/{user_id}`、`/matches/resume/{resume_id}`、`/matches/job/{job_id}`：按候选人/招聘方及资源关系授权；
- `/jobs/sync-sources`、`/analytics/rebuild`、`/analytics/sync-forum-insights`：仅管理员可触发；
- 审计反馈必须验证 `audit_record_id` / `application_id` 属于当前招聘方可以访问的岗位。

注册接口不得允许用户自行提交任意角色。可选方案：

- 普通公开注册只能成为 candidate；
- employer 需要邀请码、管理员批准或组织验证；
- 单独增加 admin，不能用 employer 代替管理员。

验收测试必须包含 IDOR：用户 A 不能读取、修改、删除用户 B 的简历、岗位、匹配、申请、邀请、消息、审计记录。

### 3.2 上传安全

不得直接使用客户端 `file.filename` 作为服务器路径。实现：

- 服务器生成随机临时文件名；
- 限制 PDF、DOCX、TXT 的 MIME、扩展名、文件大小、页数和解析耗时；
- 防路径穿越、同名覆盖、压缩炸弹和异常文件；
- 所有失败路径清理临时文件；
- 上传和模型解析失败返回稳定错误码，不返回内部堆栈或模型原始响应；
- 对简历文本设置进入模型前的长度/token 上限。

### 3.3 认证安全

补充：

- 密码最小长度和弱密码规则；
- 登录限流、防暴力破解；
- JWT 加入签发时间、唯一 ID、明确过期和可撤销策略；
- 生产环境强制安全密钥；
- WebSocket 优先使用短期 ticket，停止把长期 token 放入 URL；
- 评估从 `localStorage` 长期保存 token 迁移到更安全的 HttpOnly Cookie；
- CORS 生产环境禁止 `*` 与凭证组合；
- 日志不得记录完整简历、JWT、API Key、密码和邮箱/手机号等敏感数据。

### 3.4 隐私、合规和公平性

增加明确的数据处理规则：

- 用户授权、用途说明、保存期限、删除/导出能力；
- 删除账户和简历时处理所有关联申请、版本、证据、审计和用量记录；
- 审计功能只能给出“需要澄清/证据不足”，不能自动断言造假；
- 学校层级、学历、性别、年龄等敏感或代理变量不得成为不透明淘汰依据；
- 系统输出只能辅助人工判断，不得自动淘汰候选人；
- 为用户提供自动化处理说明、更正、撤回授权和人工复核入口；
- 公司画像和论坛数据展示来源、更新时间、样本量、置信度和合规说明；
- 外部抓取遵守 robots、站点条款和访问频率。

---

## 4. P1：强化 potential score，升级为反事实求职模拟

> 本节是产品设计说明，实际实施必须晚于第 5 节 Claim Passport 基础，以便 action 关联稳定 Claim ID、证据和版本。

### 4.1 当前问题

当前 `potential_score` 更像规则评分后的“可提升总分”，用户看到了结果，但不容易回答：

- 为什么能提升？
- 具体做什么？
- 哪些操作可以立即完成，哪些需要数月积累？
- 每项动作预计提升多少？
- 这个提升有多大置信度？
- 是补充已有真实证据，还是需要真正获得新能力？
- 为什么系统对不同经历都重复建议“增加数据”，而没有提供职责、方法、复杂度、作品证据或真实学习等替代路径？

### 4.2 目标数据结构

保留现有 `current_score` / `potential_score` 兼容字段，新增结构化模拟结果，例如：

```json
{
  "current_score": 6.4,
  "potential_score": 7.8,
  "potential_delta": 1.4,
  "confidence": 0.72,
  "confidence_basis": {
    "jd_parse_completeness": 0.8,
    "rule_coverage": 0.75,
    "simulation_stability": 0.7
  },
  "assumptions": ["岗位 JD 结构化结果准确", "用户补充内容可提供证据"],
  "actions": [
    {
      "id": "add_existing_metric",
      "title": "补充已有项目的真实性能指标",
      "category": "evidence_completion",
      "time_horizon": "immediate",
      "feasibility": "high",
      "requires_evidence": true,
      "estimated_delta": 0.3,
      "affected_dimensions": ["impact"],
      "before": 0.5,
      "after": 0.8,
      "reason": "当前项目有结果描述但没有可验证指标",
      "next_step": "回答 Claim Passport 中的结果与测量方式问题"
    }
  ]
}
```

### 4.3 动作分类

至少区分：

- `evidence_completion`：事实已经发生，只需补充真实证据；
- `resume_reframing`：忠实重组已有内容，不增加新事实；
- `skill_learning`：尚不具备，需要真实学习；
- `experience_building`：需要项目/工作经历，不能通过文字修改获得；
- `preference_change`：地点、薪资、岗位方向等由用户主动选择；
- `hard_constraint`：学历、年限等短期不可改变或不应承诺可改变。

不得将年龄、性别、学校层级等敏感、不可行动或代理特征包装成改善建议，也不得建议候选人隐瞒或伪造这些信息。

#### 4.3.1 先识别缺口，不直接生成改写

每个 action 必须先绑定一个 `issue_type`：

- `presentation_gap`：事实已存在，但表达不清；
- `relevance_gap`：经历真实，但没有映射到目标岗位任务或技能；
- `evidence_gap`：有主张，但缺少用户确认的证据；
- `differentiation_gap`：描述过于通用，没有呈现职责、方法、权衡或复杂度；
- `capability_gap`：目标能力确实尚未形成；
- `credibility_risk`：时间、角色、数字或不同来源存在冲突；
- `career_narrative_gap`：转岗、职业方向或经历之间缺少连贯解释；
- `hard_constraint`：证书、地点、签证、语言或明确年限等不能通过改写解决。

`evidence_gap` 不等于 `capability_gap`；“没有写出来”也不等于“没有能力”。系统必须通过 Claim Passport 或结构化 AI 面试继续区分。

#### 4.3.2 每个问题提供多条合法策略

在事实和产品语义允许时，同一问题应提供 2–4 条具有实质差异的策略供用户选择：

1. `relevance_alignment`：重排、取舍并映射到 JD 的任务和技能；
2. `role_clarity`：澄清本人、团队、协助和主导的边界；
3. `method_and_tradeoff`：呈现问题、方法、方案比较、限制与决策依据；
4. `scope_and_complexity`：呈现系统边界、上下游、风险、规模或协作复杂度；
5. `outcome_expression`：有来源时量化；没有数字时使用有来源的定性结果；
6. `evidence_strengthening`：关联作品、代码、证书、报告或 Claim Passport；
7. `career_narrative`：解释能力迁移、转岗路径和职业方向；
8. `portfolio_or_work_sample`：通过作品集、案例任务或可展示项目证明；
9. `skill_or_experience_building`：生成真实学习/练习/项目计划，不改写成已经具备；
10. `constraint_acknowledgement`：明确硬门槛、替代岗位或长期路径，不承诺文字优化。

`quantification` 只是 `outcome_expression` 的一个子策略，不得作为默认、兜底或对所有经历重复展示的建议。仅当服务端存在可追溯数字证据时才允许直接应用；数字尚未知时只能进入证据追问，生成的方括号模板或占位文本不得进入可写回 patch。

#### 4.3.3 岗位与公司画像的边界

建议来源必须按以下层次展示并记录版本：

- **目标岗位能力画像**：公司官方 JD 中的任务、必需/可选技能、级别和硬门槛；
- **公司工作语境画像**：官方产品、年报、工程博客、开源项目所描述的业务和技术环境；
- **证据偏好画像**：岗位更适合用项目、作品、代码、案例、证书还是结构化回答证明；
- **合作方校准信号**：仅限明确授权、去标识化且完成偏差审计的流程数据。

ESCO/O*NET 用于标准化职业、任务和技能，不直接代表某家公司的真实录用规则。禁止用公开员工简历、学校分布、年龄、性别、籍贯或历史录用结果拼接“成功候选人画像”。

### 4.4 评分规则

- 每个 action 必须通过实际评分函数重新计算，而不是让 LLM 随口给 delta；
- LLM 只负责解释和生成问题，不决定最终分数；
- 多动作组合必须重新模拟，不能简单相加，避免重复计算同一维度；
- 任何需要补充业绩数字的动作都必须标记 `requires_evidence=true`；
- 用户没有提供证据时，不能把假设内容写回简历，也不能把 potential 当成 current；
- 展示“如果……那么……”而不是“修改后一定达到……”；
- 记录评分规则版本和模拟时间，保证可复现；
- 对低样本或弱信号展示低置信度；
- `confidence` 必须由 JD 解析完整性、规则覆盖、样本充分度和模拟稳定性等可复现因素计算，禁止由 LLM 自报；
- `estimated_delta` 只表示当前评分模型内的相对变化；
- 没有完成结果校准前，禁止把 delta 描述为面试率、录用率或成功概率；
- 对组合动作重新构造完整反事实输入并重新评分，不能将单项 delta 相加；
- LLM 只生成解释、问题和候选 action，不负责给最终分数或置信度。

### 4.5 前端体验

在匹配详情中增加“可提升空间模拟器”：

- 当前分与潜力分并列；
- 可勾选动作实时查看模拟结果；
- 动作按“立即可做 / 中期成长 / 硬门槛”分组；
- 展示受影响维度、预计增量、置信度和前提；
- 需要证据的动作直接进入 Claim Passport 补充流程；
- 支持恢复默认，不自动修改简历；
- 固定说明“模型内模拟，不代表面试或录用承诺”。

前端还必须：

- 将结果分成“现在可以优化 / 需要补充证据 / 需要真实提升 / 硬门槛”；
- 每个 issue 展示推荐策略及其他可选策略，而不是自动应用唯一答案；
- 显示 `why`、目标 JD requirement、来源、是否可立即写回、预计影响维度、成本和时间范围；
- 用户切换策略后重新构造反事实输入并重新评分；
- 分开显示 `expression_delta`、`evidence_delta` 和 `capability_delta`，兼容总分可以保留，但不得暗示文案改写等于能力增长；
- 对不可写回的模板、提问和成长计划使用不同按钮与视觉状态，不得复用“采纳到简历”。

### 4.6 评测与验收

- 相同输入和规则版本输出稳定；
- 任意组合分数不超过 10，不低于 0；
- `potential_score >= current_score`，但硬性不匹配时允许 delta 为 0；
- 无证据不得提高 current score；
- 同一提升不能在多个维度重复加分；
- 至少准备 20 组固定简历/JD 的回归样本；
- 产品指标记录动作查看率、采纳率、证据补充率和后续面试转化，不只记录点击；
- 验证动作有效性、可行动性、成本、稳定性、组合一致性和事实忠实性；
- 增加“建议完成但模型外招聘结果未改善”的虚假补救用例，确保 UI 不作结果承诺；
- 分组评估获得相同模型提升所需的动作成本和可行性差异；
- delta 与真实行为结果的关系必须按区间校准，并同时报告样本量和置信区间；样本不足时只报告模型内变化。
- 对适用的 `differentiation_gap` / `presentation_gap` 样本，至少提供两条实质不同且忠实的策略；
- 固定回归集中必须包含“不适合量化”的技术、运营、设计、研究、管理和应届项目样本；
- 统计量化建议占比、策略重复率、各策略查看/选择/采纳率和人工“建议单一”评分；
- 没有数字证据时，`quantification` 不得成为可直接应用策略；存在角色或方法证据时，系统必须能提供非量化路径；
- `capability_gap` 与 `hard_constraint` 不得通过 `resume_reframing` 提高 current score；
- 任一策略必须能回指 `issue_id`、目标 requirement、输入 Claim/answer 和规则/模型版本。

---

## 5. P1：增加 Claim Passport（履历主张护照）

### 5.1 产品定义

Claim Passport 不是区块链证书，也不是“真实性判决”。它是每条履历主张的可追溯记录，回答：

- 这条主张来自简历哪个位置、哪个版本？
- 原始文本是什么？
- AI 做过哪些改写？
- 用户提供了哪些补充说明或证据？
- 招聘方提出过什么问题？
- 当前状态是已说明、待澄清、存在冲突还是已复核？
- 哪些岗位和申请使用了这个版本？

### 5.2 MVP 字段

建议建立正式关系表，而不是继续把所有内容塞入 `pipeline_meta` JSON。至少包含：

#### `resume_claims`

- `id`（稳定 claim ID）；
- `resume_id`；
- `resume_version_id` 或版本号；
- `section`、`item_index`、`field_path`；
- `claim_type`；
- `original_text`、`current_text`；
- `status`；
- `created_at`、`updated_at`。

#### `claim_evidence`

- `id`、`claim_id`；
- `evidence_type`：user_statement / metric_context / document_reference / employer_review；
- `summary`；
- `source`；
- `provided_by`；
- `verification_status`；
- `created_at`。

MVP 不建议直接保存身份证、工资单等高敏感原件。先保存结构化说明和可撤回引用；如以后上传原件，必须增加独立加密存储、访问审计和保留期限。

#### `claim_revisions`

- 原文、改写后文本；
- 改写模式；
- 使用的 evidence IDs；
- 模型/提示词/规则版本；
- 忠实度检查结果；
- 创建者和时间。

#### `claim_application_links`

- `claim_id`；
- `application_id`；
- 投递时的文本快照；
- 审计结果和复核状态。

### 5.3 MVP 状态建议

MVP 不把证据结论和工作流进度混在一个八态字段中，拆成两层：

**证据语义 `evidence_state`：**

- `supported_by_user_evidence`：有用户提供的来源支持，不等于第三方认证；
- `not_enough_information`：证据不足；
- `conflict_detected`：不同来源存在冲突，需要人工处理。

**工作流语义 `workflow_state`：**

- `open`；
- `answered`；
- `reviewed`；
- `withdrawn`。

状态迁移必须由后端状态机控制并记录事件历史，不得仅由前端修改字符串。`clarified` 只能表示用户已完成说明，`employer_reviewed` 只能表示招聘方看过并处理了问题，两者都不能在 UI 中显示成“已验证真实”或“认证通过”。

### 5.4 与现有功能整合

- 简历体检发现表达、相关性、证据或一致性问题时创建或更新 claim；不得把所有问题折叠为“未量化”；
- evidence follow-up 的回答写入 claim evidence；
- faithful rewrite 写入 claim revision；
- 招聘方 clarification 使用同一个稳定 claim ID；
- credibility audit 读取 Claim Passport，但审计结果不能覆盖用户原始证据；
- potential score 的 `evidence_completion` 动作链接到对应 claim；
- 简历应用建议前展示使用了哪些证据；
- 投递时保存 Claim Passport 快照，后续修改不能悄悄改变历史申请。

### 5.5 前端页面

候选人端：

- 每份简历增加“履历主张”页签；
- 按状态筛选；
- 展示原文、当前文本、证据、修改历史和待回答问题；
- 用户可撤回自己的补充说明，并看到对已投递申请的影响。

招聘方端：

- 仅显示与该岗位/申请有关的 Claim Passport 快照；
- 明确区分用户自述、系统推断和招聘方复核；
- 不展示候选人未授权且与当前申请无关的信息。

### 5.6 验收标准

- claim ID 在简历改写和前后端流程中保持稳定；
- 任一 AI 改写都能追踪到原文和证据；
- 无证据改写不能提升为“已验证”；
- UI 明确区分“用户自述”“有用户证据支持”“招聘方已复核提问”“信息不足”和“存在冲突”；
- 历史申请使用快照，不受当前简历修改污染；
- 不同招聘方不能看到彼此的提问、内部反馈或无关申请；
- 删除/撤回数据有明确且经过测试的传播规则。

---

## 6. P1：数据库与一致性

### 6.1 引入版本化迁移

- 使用 Alembic 或同等级方案替换启动时手写 schema alignment；
- 为当前生产/开发数据库生成可验证的基线迁移；
- 迁移必须可重复执行并提供回滚策略；
- 应用启动不再承担任意 DDL 变更。

### 6.2 约束与索引

检查并补充：

- 同一候选人对同一岗位只有一个有效申请；
- 同一岗位/简历不能存在重复待处理邀请；
- MatchResult 的 `(resume_id, job_id)` 唯一约束；
- 常用外键、状态、时间排序索引；
- 状态字段约束或枚举；
- Claim Passport 的稳定 ID 与版本约束；
- 更新时间并发控制。

### 6.3 删除策略

明确每个实体采用：级联删除、软删除、匿名化或保留审计快照。特别测试：

- 删除简历；
- 删除岗位；
- 删除账户；
- 删除已有申请/邀请/审计/Claim Passport 的实体；
- 用户撤回证据。

所有删除必须事务化，不能只删除 MatchResult 后依赖数据库碰运气。

---

## 7. P1：后端架构和性能

### 7.1 拆分大型模块

当前 `main.py`、`application_routes.py`、匹配和可信度模块过大。按领域逐步拆分：

- router：HTTP 输入输出；
- service：业务流程和状态机；
- repository/query：数据库访问；
- domain：评分、Claim、申请状态；
- integrations：LLM、邮件、抓取、Redis；
- schemas：Pydantic 请求和响应。

禁止只为“文件变短”机械拆分；每个模块必须有清晰责任和测试边界。

### 7.2 异步和后台任务

- 将同步 OpenAI 客户端替换为异步调用，或放入受控线程/任务队列；
- 简历解析、全量匹配、论坛抓取、分析重建移入后台 worker；
- API 返回 job ID 和进度，前端轮询或订阅；
- 增加超时、有限重试、幂等键、取消和失败恢复；
- scheduler 独立部署，避免多 worker 重复执行；
- SSE 从进程内 EventBus 迁移到 Redis Pub/Sub/Streams，支持多实例。

### 7.3 查询性能

- 浏览岗位分页，不得一次加载全表后在 Python 中筛选；
- 匹配生成避免 resume × job 循环中逐条查询数据库；
- 列表接口消除 N+1；
- 大型 JSON 响应只返回页面需要的字段；
- 对昂贵评分增加基于输入版本的缓存与失效规则。

### 7.4 PR 5.5：产品与代码收敛

安全问题逐点修复后，必须安排一个不增加功能的收敛批次，避免授权 helper、状态判断、兼容分支、UI 文案和 API 形状继续叠加成补丁集合。

收敛原则：

- 用候选人与招聘方两条核心旅程约束页面、接口和领域服务；
- 身份授权、Application/Claim 状态机、投递快照、suggestion 可应用性、评分版本分别只有一个权威实现；
- 路由只处理输入输出，领域规则进入明确 service；前端重复请求、状态映射和澄清逻辑进入 feature API/hook/util；
- 统一 Claim、澄清、已说明、证据不足、可信度审计、可提升空间模拟等术语；
- 统一状态 enum、错误 envelope、时间、分页、幂等和任务进度契约；
- 兼容路径必须登记调用方、移除条件和截止批次，不能永久保留无测试旁路；
- 建立候选人和招聘方各一条端到端冒烟测试；
- 不进行全仓重写，不批量格式化，不关闭 lint/安全规则。

验收时应提交：模块边界图、术语表、兼容路径清单、重复规则删除记录、两条端到端测试结果，以及 lint 基线变化。PR 5.5 未完成前，不应把当前代码和界面描述为稳定成品。

---

## 8. P1：前端质量和体验

当前基线：生产构建成功，但 ESLint 有 25 个错误、14 个警告；主 bundle 约 1.43 MB。

任务：

- 修复全部 lint error；warning 必须逐项判断，不能批量关闭规则掩盖问题；
- 修复 `Candidate/Dashboard.jsx` 中未定义的 `Space`；
- 处理 Hook 闭包、缺失依赖、重复请求和 effect 内同步派生状态；
- 增加全局 API 错误处理、401 自动退出、403/429/402 友好提示；
- 统一 loading、empty、error、retry 状态；
- 路由级 lazy loading 和代码分割；
- 不再从 `localStorage user_id` 决定服务端资源归属；
- 为消息、SSE/WebSocket 重连增加断线状态和退避；
- 对 Claim Passport 和反事实模拟提供移动端可用布局；
- 统一中文术语：主张、证据、待澄清、已复核、潜力分等。

验收：

- `npm run lint` 通过；
- `npm run build` 通过；
- 关键页面无控制台错误；
- 首屏和主要路由 bundle 明显下降；
- Chrome 与主流移动端尺寸完成基本回归。

---

## 9. P1：测试与持续集成

### 9.1 后端

建立独立测试数据库，至少包含：

- 注册、登录、角色和管理员权限；
- 所有资源的越权访问；
- 上传文件类型、路径穿越、大小限制；
- 投递和 Claim 状态机的合法/非法迁移；
- 重复投递、重复邀请、并发更新；
- 删除简历/岗位/账户的关联行为；
- Claim Passport 版本、证据和快照；
- potential 模拟的确定性、边界、去重和证据约束；
- LLM 无 Key、超时、非法 JSON、限流和降级；
- 配额并发下不能超卖。

### 9.2 前端和端到端

- 关键组件测试；
- 候选人注册 → 上传 → 匹配 → 投递；
- 招聘方查看 → 审计 → 发起澄清；
- 候选人回复 → 招聘方复核 → 面试邀请；
- potential 动作进入 Claim Passport；
- 权限错误、模型不可用和配额耗尽流程。

### 9.3 CI 门禁

每次提交必须运行：

- Python lint/format/type check；
- 后端单元与集成测试；
- 前端 lint、测试和 build；
- 迁移升级测试；
- 依赖安全扫描和 secret scan。

任何一步失败不得合并。

---

## 10. P2：AI 质量、可观测性和成本

### 10.1 固定评测集

准备脱敏且人工标注的数据集，持续评估：

- 简历/JD 字段解析准确率；
- 匹配 Top-K 质量；
- potential action 合理性与分数校准；
- 多路径策略覆盖率、策略多样性、量化建议占比和缺口分类准确率；
- 忠实改写事实保持率；
- 可信度审计误报率和漏报率；
- Claim 与证据匹配准确率；
- 不同行业、学历和人群之间的公平性差异。

试点前建立最低公平性协议：

- 按岗位族统计分数分布、Top-K 进入比例、人工复核和后续结果；
- 在具备合法处理基础时使用去标识化分组数据评估 selection rate / impact ratio；不得为了评测擅自扩大敏感信息收集；
- 检查学校层级、地区、语言风格等代理变量；
- 评估不同群体获得相同模型提升所需的动作成本和可行性；
- 招聘方反馈、面试邀请和历史录用只能作为可能带偏差的观察信号，不能直接作为能力真值；
- 所有报告同时给出样本量、置信区间、规则/模型版本和已知限制；
- 保留人工介入、说明、更正和申诉能力。

### 10.2 LLM 治理

- 统一 LLM gateway，不要各模块重复创建客户端；
- 记录模型、提示词版本、延迟、token、成本和结果状态；
- 敏感数据最小化后再发给模型；
- 对 Prompt Injection 做输入隔离；
- 结构化输出必须经过 Pydantic 校验；
- 原始模型响应不直接返回用户；
- 支持模型降级、熔断和供应商切换。

### 10.3 监控

至少建立：

- API 请求量、错误率和 P95；
- LLM 调用成功率、延迟、token 和费用；
- worker 队列长度和失败任务；
- 数据库连接、慢查询；
- 登录失败和异常权限请求；
- 上传失败、解析失败；
- potential 模拟和 Claim Passport 的业务转化漏斗。

---

## 11. P2：商业化与产品验证

先聚焦一个主价值：

> 帮助候选人生成可追溯、不编造、能经得起招聘方追问的岗位定制简历。

不要先做全行业大而全招聘市场。小规模试点重点测量：

- 简历建议采纳率；
- 真实证据补充率；
- potential action 完成率；
- 招聘方审计误报率；
- 澄清完成率和平均时间；
- 面试邀请转化；
- 每位活跃用户的模型成本；
- 候选人与招聘方付费意愿。

配额系统后续应从“固定调用次数”升级为套餐、组织额度、成本预算和异常使用保护，但在支付上线前先验证价值和成本。

---

## 12. 建议实施批次

本节与 `CURSOR_EXECUTION_BACKLOG.md` 使用同一编号，后者是逐批执行和验收的唯一权威清单。

| 批次 | 内容 | 当前状态 |
|---|---|---|
| PR 0 | 测试数据库隔离、fixture、权限回归骨架 | 阶段回归通过；收口补强中 |
| PR 1 | 审计与反馈跨租户权限封堵 | 阶段回归通过；授权链收口中 |
| PR 2 | 忠实写回、占位采纳、多 Claim 正确绑定 | 阶段回归通过；证据真相源收口中 |
| PR 3 | 状态机、申请简历不可变、邀请一致性 | 进行中（部分实现） |
| PR 4 | 全接口鉴权、上传、认证、删除安全 | 已完成并于 2026-07-25 重新验收 |
| PR 5 | 原子配额、WebSocket 凭证、忠实度校验 | 已完成并于 2026-07-25 验收 |
| PR 5.5 | 产品与代码收敛：模型、术语、契约和领域边界 | 已完成并于 2026-07-25 最终验收 |
| PR 6 | 一键启动和客户交付 | 已完成并于 2026-07-25 最终验收 |
| PR 7 | 前端质量、Alembic、CI、后台任务和公平性基线 | 部分完成（核心工程门禁通过；自动化全链路 E2E、全量异步化、公平性完整协议及远端 CI 待关闭） |
| PR 8 | Claim Passport MVP | 未开始 |
| PR 9 | 多路径岗位适配优化、Potential Score 反事实模拟与 delta 校准 | 未开始 |

关键顺序约束：

- PR 3–5 未完成前，不处理真实客户简历；
- PR 5.5 在对外成品交付前统一模型、术语、API 契约和代码边界；
- PR 6 提供 Web SaaS/私有化一键交付，不把多终端启动留给客户；
- PR 7 先建立迁移和公平性基线；
- PR 8 先建立稳定 Claim ID、证据和投递快照；
- PR 9 再让多路径 Potential action 关联 Claim Passport，区分表达/证据/能力改善，并执行策略多样性、delta 校准与虚假承诺测试。

---

## 13. Cursor 每次完成任务后的固定输出

每个任务完成后必须报告：

1. 修改了哪些文件和原因；
2. 是否有数据库迁移、配置变化或兼容影响；
3. 新增了哪些测试；
4. 实际执行的测试命令与结果；
5. 尚未解决的问题和风险；
6. 如何人工验收；
7. 确认没有覆盖或回滚任务开始前已有的用户改动。

若发现实现需要改变产品规则、删除数据、重写现有未提交代码或引入新的外部付费服务，先停止并询问用户，不得自行决定。

---

## 14. 研究与标准依据

以下资料用于约束方案，不应只作为宣传引用：

- [OWASP API Security Top 10 API1:2023](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)：所有客户端对象 ID 都需要服务端对象级授权；
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)：Claim Passport 采用 Entity / Activity / Agent 与派生关系表达溯源；
- [Ustun et al. (2019), *Actionable Recourse in Linear Classification*](https://www.berkustun.com/papers/actionable-recourse/ustun2019recourse.pdf)：区分可行动、条件可行动和不可变特征；
- [Karimi et al. (2022), *A Survey of Algorithmic Recourse*](https://doi.org/10.1145/3527848)：反事实目标不天然等于现实可执行建议，需考虑可行性、成本、因果和公平性；
- [Raghavan et al. (2020), *Mitigating Bias in Algorithmic Hiring*](https://arxiv.org/abs/1906.09208)：招聘反馈和历史录用数据可能继承既有偏差，必须验证目标与岗位相关性；
- [OPM Job Analysis](https://www.opm.gov/policy-data-oversight/assessment-and-selection/job-analysis/)：从实际岗位任务连接所需 competencies、选拔与训练需求，支持使用“岗位能力画像”替代历史员工“成功画像”；
- [*Measuring Attribution in Natural Language Generation*](https://direct.mit.edu/coli/article/49/4/777/116438/Measuring-Attribution-in-Natural-Language) 以及事实一致性研究：写回内容应拆为原子事实并逐项检查来源支持；
- [NIST AI RMF 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10)：持续执行 Govern / Map / Measure / Manage，记录有效性、透明度、隐私与有害偏差；
- [《中华人民共和国个人信息保护法》第二十四条](https://www.samr.gov.cn/wljys/gzzd/art/2023/art_3ef1e889c1e644d4b65b5f5c7f432386.html)：自动化决策应透明、公平、公正，并提供说明与拒绝仅自动化决策的能力；
- [Docker Compose 官方应用模型](https://docs.docker.com/compose/intro/compose-application-model/)：用于开发、演示和单机私有化一键启动；
- [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) 4.2 / 5.1：App 不能只是重新包装的网站，并必须满足隐私政策、数据最小化、第三方 AI 数据共享披露、同意撤回和 App 内账户删除。

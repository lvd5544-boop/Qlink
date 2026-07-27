# AI Job Platform 合并整改执行单（Cursor 直接执行版）

> 本文件将代码审查 Findings、整体成熟度评价以及 `CURSOR_REMEDIATION_PLAN.md` 合并为一份有顺序、有验收标准的实施清单。

## 1. 给 Cursor 的总指令

先完整阅读：

- `CURSOR_EXECUTION_BACKLOG.md`（本文件）；
- `CURSOR_REMEDIATION_PLAN.md`（完整产品与工程规划）；
- `CURSOR_PR0_PR3_CLOSURE_SPEC.md`（PR0–PR3 尚未关闭的安全与数据阻断项）；
- `CURSOR_DEFINITION_OF_DONE.md`（所有批次的实施与验收协议）；
- 当前批次的专用实施规格；PR3 使用 `PR3_IMPLEMENTATION_SPEC.md`；
- `AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`（数据、可信度推理、AI 面试和岗位推荐设计；仅在对应后续批次使用）；
- 当前 `git status` 和相关代码。

执行规则：

1. 当前工作区已有大量已暂存、未暂存和未跟踪改动，全部视为用户资产。禁止 reset、checkout、覆盖或顺手格式化无关文件。
2. 不允许一次完成整份清单。严格按 PR/批次执行，每次只做一个批次，完成测试和人工验收后再进入下一个批次。
3. 修改前先输出：本批次目标、涉及文件、数据库迁移、兼容风险、测试计划。
4. 优先修复信任边界和数据正确性，再做一键部署、Claim Passport 和 Potential Score。
5. 所有权限由后端判断。不得信任前端的 `user_id`、`employer_id`、`role`、资源 ID 或按钮是否隐藏。
6. 所有写回简历的 AI 内容必须有事实来源。无证据时只能提问、提示或模拟，不能写回。
7. 禁止通过关闭 lint/安全规则、捕获并吞掉异常、保留后门参数等方式让测试“通过”。
8. 如果修复需要改变产品规则或删除/迁移真实数据，先停下并向用户确认。

每个批次完成后固定报告：

- 修改文件与原因；
- 行为变化和兼容影响；
- 数据库迁移及回滚方式；
- 新增测试；
- 实际执行的命令与结果；
- 人工验收步骤；
- 未解决风险；
- 确认未覆盖任务开始前的用户改动。

---

## 2. Findings 核验结论

### 已通过阶段性回归，但收口审计重新打开

截至 2026-07-24：

- PR 0 原阶段已建立测试数据库隔离、权限 fixture 和 Findings 回归骨架；
- PR 1 原定向用例已封堵直接的审计简历访问与审计反馈跨租户权限；
- PR 2 原定向用例已禁止无证据角色升级、占位文本写回和多 Claim 错绑；
- PR 2 定向回归为 `3 passed`，完整后端测试为 `39 passed, 1 xfailed`，只剩 PR 3 的一个 strict XFAIL；
- 前端生产构建通过；全局 lint 仍有 25 个 errors、14 个 warnings，属于既有质量债，必须在 PR 5.5/PR 7 收敛，不得把“能构建”等同于“前端质量门禁通过”；
- 后续 `CURSOR_PR0_PR3_CLOSURE_SPEC.md` 发现此前测试覆盖不足：自动创建申请可能反向扩大简历审计授权、忠实写回仍需服务端 evidence 真相源；因此 PR 1/PR 2 的“已完成”只代表原定向用例通过，不代表安全收口；
- PR 3 已出现部分实现与测试文件，但尚未按产品语义、迁移、并发和完整 Definition of Done 验收；
- 2026-07-24 当前旧测试集为 `49 passed`；它仍把“招聘方人工关闭”断言为 `clarified`，因此全绿只能证明旧契约一致，不能证明产品语义正确；
- 当前必须完成 PR0–PR3 收口，不得跳到 PR 4。

### 已确认，尚待修复

1. 通用状态接口允许绕过 Claim 澄清工作流。
2. 澄清与邀请流程会静默替换已存在申请的 `resume_id`。
3. 配额采用先 count 后记账，并发时可超额。
4. 面试 WebSocket 客户端把长期 JWT 放在 URL。
5. 非严格忠实度检查可被少量原文子串加大量虚构内容绕过。
6. 多个旧岗位、匹配、同步接口仍缺少完整鉴权和资源归属。
7. 上传文件名、数据删除、数据库迁移、异步 LLM、测试和交付仍未达到试点要求。
8. 产品术语、状态判断、权限 helper、前后端契约和兼容分支尚未完全收敛，继续逐点补丁会增加“改动堆砌”风险。

### 未证实，不得按“已确认缺陷”盲改

“`/{application_id}/events` 抢占 `/stream/me`”当前从路由形状上不成立：前者要求第二段固定为 `events`，而 `/stream/me` 的第二段是 `me`。Cursor 应：

1. 添加路由可达性测试，证明 `GET /applications/stream/me` 命中 `user_events_sse`；
2. 添加 `GET /applications/{id}/events` 的独立测试；
3. 可以将静态路由放在动态路由前以提升可读性，但不得声称这是已复现的故障；
4. 若测试确实失败，再依据实际匹配结果修复并记录原因。

---

## 3. 执行顺序总览

| 批次 | 目标 | 状态 | 是否阻断真实试点 |
|---|---|---|---|
| PR 0 | 建立测试基线和权限测试工具 | 阶段回归通过；收口补强中 | 是 |
| PR 1 | 审计与反馈跨租户权限封堵 | 阶段回归通过；授权链收口中 | 是 |
| PR 2 | 忠实写回、占位采纳、多 Claim 绑定 | 阶段回归通过；证据真相源收口中 | 是 |
| PR 3 | 状态机、申请简历不可变、邀请一致性 | 进行中（部分实现） | 是 |
| PR 4 | 全接口鉴权、上传、认证、删除安全 | 已完成并于 2026-07-25 重新验收 | 是 |
| PR 5 / 5.1 | 原子配额、计费权益、面试用途同意、WebSocket/忠实度 | 已完成并于 2026-07-25 最终验收 | 是 |
| PR 5.5 | 产品与代码收敛：统一模型、术语、契约和领域边界 | 已完成并于 2026-07-25 最终验收 | 对外成品交付前 |
| PR 6 | 一键启动与客户交付 | 已完成并于 2026-07-25 最终验收 | 是 |
| PR 7 | 前端质量、CI、迁移、后台任务和公平性基线 | 部分完成（本地：E2E/队列化/公平性协议已关；**远端 GitHub Actions 全绿仍阻断**；不得开始 PR8） | 试点扩容前 |
| PR 8 | Claim Passport MVP | **部分完成**（本地功能、PG up/down/up、专项测试与浏览器 E2E 已复验；远端 CI/push 未闭合，详见 `PR8_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`） | 核心产品基础 |
| PR 9 | Potential Score 反事实模拟增强 | **部分完成**（本地骨架/API/四栏壳与 25 项定向测试通过；完整反事实输入、前端工作流、规格级跨岗回归与远端 CI 未闭合；详见独立验收 `PR9_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`） | 核心产品增强 |

在 PR 3–6 完成前，不得宣称产品可安全处理真实客户简历；PR 5.5 未完成前，不得把当前界面和代码结构描述为稳定成品。PR 8 必须先于 PR 9，因为反事实动作需要稳定 Claim ID、证据和版本关系。

---

## 4. PR 0：先建立可验证基线

**状态：已完成（2026-07-22）。**

### 目标

不改变业务行为，先让后续安全修复可以通过自动化测试证明。

### 任务

1. 固化 Python 开发/测试依赖，确保全新环境能运行 pytest。
2. 建立独立测试数据库；测试不得连接或修改开发数据库。
3. 提供 candidate A、candidate B、employer A、employer B、admin 的 fixture。
4. 提供两个岗位、两份简历、匹配、申请、审计记录和 Claim 线程 fixture。
5. 建立 FastAPI 集成测试客户端与认证 helper。
6. 记录当前前端基线：`npm run lint`、前端测试、`npm run build`。
7. 将现有工作区测试失败区分为“基线已有”和“本批次新增”，不得顺手重构所有代码。

### 必须新增的安全测试骨架

- A 不能读取/写入 B 的简历、岗位、申请、消息、审计和反馈；
- 未登录用户不能调用非公开接口；
- candidate、employer、admin 的角色矩阵；
- 任意资源 ID 不存在时不泄露资源是否属于其他租户。

### 验收

- 后端测试可在一条命令中运行；
- 测试数据与开发数据完全隔离；
- 后续每个 Finding 都有一个先失败、修复后通过的回归测试。

---

## 5. PR 1：审计与反馈跨租户权限封堵

**状态：已完成并于 2026-07-23 复核。对应两个回归测试已从 strict XFAIL 转为正常 PASS。**

### 5.1 修复任意简历可信度审计

涉及：`backend/app/application_routes.py` 的岗位-简历审计接口。

当前问题：只检查岗位属于当前招聘方，随后直接读取任意简历。

建立统一授权函数，例如语义上等价于：

`ensure_employer_can_access_resume_for_job(db, employer_id, job_id, resume_id)`

MVP 默认允许条件：

- 存在与当前 `job_id + resume_id` 精确关联的 JobApplication；并且
- 该申请的 `employer_id`、岗位 owner 均为当前招聘方。

注意：全局 MatchResult 不能自动视为候选人授权，因为当前系统会对大量简历/岗位自动生成匹配。若产品需要招聘方主动搜索人才，必须先增加明确的候选人可见性/授权模型，例如：

- `candidate_profile_visibility`；
- 候选人选择公开范围；
- 可见岗位/组织范围；
- 授权时间和撤回记录。

在该模型完成前，匹配本身不能授权读取简历或生成可信度审计。

接口响应对无权访问统一返回 404 或项目选定的防枚举响应，避免泄露简历存在性。

### 5.2 修复审计反馈归属

写入反馈前必须：

1. 加载 `CredibilityAuditRecord`；
2. 确认 `record.employer_id == current_user.id`；
3. 若传 `application_id`，加载申请并确认属于当前招聘方；
4. 确认申请、岗位、简历与审计记录互相一致；
5. 若传 `finding_id/claim_id`，确认它存在于该审计报告或允许的 Claim 集合；
6. 禁止客户端覆盖 `employer_id` 等服务端字段。

建议给反馈添加防重复约束或幂等规则，例如 `(audit_record_id, employer_id, finding_id)`。

### 测试

- employer A 审计自己的申请成功；
- employer A 审计 employer B 的申请/简历失败；
- employer A 使用自己的 job + 任意 resume 失败；
- 只有 MatchResult、没有候选人授权或申请时失败；
- employer A 向 employer B 的 audit record 写反馈失败；
- 混用 audit record A 与 application B 失败；
- 合法反馈成功且训练数据租户一致。

---

## 6. PR 2：忠实写回与多 Claim 正确绑定

**状态：已完成（2026-07-23）。**

验收记录：

- 三个 PR 2 定向安全回归均正常 PASS；
- 完整后端测试为 `39 passed, 1 xfailed`，退出码为 0，只剩 PR 3 的一个 strict XFAIL；
- 前端 production build 成功；
- 全局 lint 尚未通过，相关存量问题进入 PR 5.5/PR 7，不通过关闭规则规避。

### 6.1 禁止建议编造角色

涉及：`backend/app/resume_consistency.py`。

删除无依据的固定文案：

- “担任…技术负责人”；
- “主导研发落地”；
- 任何原文/用户证据中不存在的职位、责任、数字、技术、结果。

新规则：

1. 如果原始 `position/title` 明确包含技术角色，只能用已有角色做忠实重组；
2. 如果角色不明确，只生成“需要确认角色边界”的问题，不生成可直接应用的 patch；
3. 建议可给写作框架，但框架不能作为 `patch.value`；
4. 需要用户回答后，走 evidence follow-up / Claim Passport，再生成可写回版本；
5. 所有自动 patch 必须保留原文事实，不能从期望岗位反推过去经历。

测试至少覆盖：工程意向 + 产品措辞但原文无技术负责人时，输出不得出现“技术负责人/主导研发”。

### 6.2 禁止占位文案覆盖简历

涉及：

- `frontend/src/components/SuggestionDiffCard.jsx`；
- 后端 preview/apply suggestion；
- suggestion store 和证据状态。

前端修复：

1. 不得把 `append_quantification` 静默改成 `fill_field`；
2. `requires_evidence` / `needs_followup` 且未完成证据追问时，禁用“采纳”；
3. “采纳”替换成“先补充证据”；
4. 占位文本只能用于 UI 提示，不能进入 patch；
5. 证据追问完成后使用后端返回的、带 evidence 关联的 patch。

后端防御必须独立成立，不能只修前端：

1. apply 时加载数据库中的 suggestion，不信任客户端任意改写 action；
2. 校验客户端 patch 与存储 suggestion 的类型、目标字段一致；
3. `requires_evidence=true` 时必须有完成的 evidence/clarification 引用；
4. 拒绝 null、空值、“需先完成”“待补充”等占位文本；
5. 对 `fill_field` 同样执行事实与目标字段校验，不能成为绕过 append 护栏的通道；
6. 失败时不能把 suggestion 标记 applied。

测试：恶意客户端直接把 append 改成 fill_field 仍返回 4xx，原简历保持不变。

### 6.3 多 Claim 回复必须显式绑定

涉及候选人 AppliedJobs 与 clarification-response。

前端：

- 将每个开放 Claim 单独展示；
- 用户选择或进入某个 Claim 后回复；
- POST 必须发送 `body + claim_id`；
- 成功后只更新该 Claim；
- 仍有开放 Claim 时显示 `needs_clarification`，不能显示全部已澄清。

后端：

- 有 Claim 线程的请求必须校验 `claim_id`；
- 多个开放 Claim 时缺少 claim_id 必须 422/400，不能选择“最新一个”；
- claim_id 必须属于该申请且处于 open 状态；
- 已关闭、未知或属于其他申请的 claim_id 必须失败；
- 只关闭被回答的 Claim；
- 所有 Claim 关闭后由状态机计算 clarified；
- clarification answer 写入正确 Claim，并保留 request_message_id。

为单一旧版澄清消息保留兼容时，只允许“恰好一个明确开放 Claim”自动绑定，并记录兼容路径日志；不允许多 Claim 回退。

---

## 7. PR 3：状态机与申请简历不可变

**本批次的文件级、函数级、状态迁移、数据兼容和测试权威规格见 `PR3_IMPLEMENTATION_SPEC.md`。本节只保留摘要；Cursor 不得只读本节后直接编码。**

### 7.1 禁止通用状态接口绕过业务动作

通用 status PATCH 只允许没有专用业务动作的招聘流程状态。以下状态不能由任意角色直接设置：

- `needs_clarification`：只能由“成功创建至少一个 Claim 澄清请求”产生；
- `clarified`：只能由 Claim 状态机在所有开放 Claim 得到有效回复后计算；
- `interview_invited`：只能由成功创建邀请产生。

候选人不得直接 PATCH `clarified`。招聘方如需“人工关闭澄清”，应提供明确动作：

- 记录关闭人、原因和时间；
- 关闭或标记相关 Claim；
- 不伪装成候选人已回复。

建立状态迁移表和单一 domain service，禁止路由中到处直接赋值 `app.status = ...`。

### 7.2 已投递申请的 resume_id 不可静默改变

以下路径不得覆盖已有申请的 `resume_id`：

- apply_job 发现重复申请；
- `_get_or_create_application_for_clarification`；
- invitation `_get_or_create_application`。

短期规则：申请创建后 `resume_id` 不可变。若用户主动更换简历，必须通过显式接口和确认流程，并保留：

- 原简历/版本快照；
- 新版本；
- 更换人和时间；
- 已发送给招聘方的历史内容不被覆盖。

优先设计 `resume_version` / application snapshot，而不是让申请永远引用会持续变化的 `Resume.parsed_json`。

招聘方从人才池发起澄清或邀请时：

- 若已有该岗位申请，必须使用申请原简历；
- 若指定了另一份简历，返回冲突，不能替换；
- 若没有申请且产品允许主动邀约，创建明确标记为 sourced/invited 的记录，并满足候选人可见性授权。

### 测试

- candidate/employer 直接 PATCH clarified 失败；
- 无 Claim 请求不能进入 needs_clarification；
- 回复一个/多个 Claim 的状态准确；
- 邀请动作成功后才进入 interview_invited；
- 重复申请、澄清、邀请均不改变原 resume_id；
- 历史审计仍指向投递时快照。

---

## 8. PR 4：全接口安全与数据完整性

**状态：已完成（2026-07-25 安全复审修复后重新验收）。详见 `PR4_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`。**

### 8.1 统一审计旧接口

重点修复：

- `/post-job` 不再接受可信的任意 employer_id；
- 岗位列表改为 `/jobs/mine` 或验证本人；
- 岗位更新/删除验证 owner；
- 匹配生成与查询按 candidate/employer 关系授权；
- 数据同步、论坛同步、analytics rebuild 仅 admin；
- 注册不得由用户直接指定 employer/admin；
- 资源查询统一防 IDOR；
- 浏览岗位可公开，但不得泄露不应公开的联系人或内部字段。

建立复用的权限 dependency/service，不要每个路由复制不一致的 if。

### 8.2 安全上传

- 服务端随机临时文件名；
- 防 `../` 路径穿越与并发覆盖；
- MIME、扩展名、大小、页数、解压/解析资源限制；
- 解析和模型输入长度上限；
- 全失败路径清理文件；
- 原始模型响应和内部路径不得返回客户端。

### 8.3 删除与隐私

明确简历、岗位、账户删除时，对 suggestion、variant、match、application、invitation、message、audit、usage、Claim Passport 采取：级联、软删除、匿名化或依法保留。

删除必须事务化并有集成测试。不得只删除 MatchResult。

### 8.4 认证

- 密码最小强度；
- 登录限流；
- employer 审核/邀请码；
- admin 独立角色；
- JWT 生命周期和撤销策略；
- 生产环境 CORS 白名单；
- 日志脱敏。

---

## 9. PR 5：原子配额、WebSocket 和忠实度

**状态：已完成（2026-07-25）。详见 `PR5_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`。**

### 9.1 原子配额预占

当前 `check_quota -> LLM -> record_usage` 存在竞态。

实现原子 reserve/finalize 模型：

1. 每个请求有 idempotency key；
2. LLM 前在数据库事务中原子预占额度；
3. 并发更新使用条件 UPDATE、UPSERT 或行锁，保证用量不超过 quota；
4. 成功后 finalize 实际 units/cost；
5. 失败时按明确规则 release 或记为失败消耗；
6. 重试同一 idempotency key 不能重复扣费；
7. 记录 reserved/succeeded/failed/released 状态。

测试使用并发请求证明限额为 N 时最多 N 个请求获得预占。

### 9.2 WebSocket JWT 不进入 URL

前端：

- 连接 URL 不带 `token`；
- WebSocket open 后第一条发送 `{type: "auth", token: "..."}`；
- 收到 auth_ok 后才允许发送面试消息；
- auth 失败/超时关闭连接并提示重新登录。

后端：

- 首条消息认证设置短超时；
- token 与 URL user_id 必须一致；
- resume/application 必须属于或授权给该用户；
- 生产环境关闭 query token 兼容；若保留开发兼容，必须由显式环境开关控制且默认关闭。

长期建议换短期、单用途、可撤销的 WS ticket。

### 9.3 强化忠实度验证

不能以“存在任意 4 字原文子串”证明整句忠实。

最低要求：

- 对数字、百分比、金额、时间、规模、专有名词和角色进行来源校验；
- 生成的每个事实片段必须能追踪到原文或用户回答；
- 对长句采用覆盖率/片段对齐，少量公共子串不能放行大量新增内容；
- 写回路径强制使用严格模式；非严格模式最多用于不会保存的预览；
- 检查失败使用严格拼接兜底或要求用户确认，不能静默接受；
- 保存时记录 evidence IDs 和 fidelity 结果。

回归用例必须包含：

- 前半句复制原文、后半句编造业绩；
- 保留 4 字原文但新增百分比；
- 同义忠实改写；
- 用户回答中真实出现的数字；
- 角色升级（参与者 → 负责人）应拦截。

---

## 10. PR 5.5：产品与代码收敛

**状态：已完成（2026-07-25）。详见 `PR5_5_IMPLEMENTATION_AND_VERIFICATION_REPORT.md` 与 `PR6_FINAL_GATE_CLOSURE.md`。**

### 目标

在继续做部署和产品增强前，把前几轮安全修复收敛成统一的产品模型和代码结构，消除“每发现一个问题就增加一个旁路、兼容分支或重复判断”的补丁感。本批次不增加新功能，不做全仓重写。

### 任务

1. 先画出候选人和招聘方两条 canonical journey：上传/建议/投递/澄清，以及岗位/申请/审计/邀请。每个页面和接口必须能映射到其中一个明确步骤。
2. 建立单一事实来源：
   - 身份与对象权限统一由 authorization service/helper 判断；
   - Application 与 Claim 状态只由领域状态机迁移；
   - 已投递简历使用 application snapshot/version，不与可编辑工作简历混用；
   - suggestion 的证据要求、可应用性和写回结果由后端权威决定；
   - scoring 版本、Claim ID 和 evidence reference 使用稳定模型。
3. 统一前后端术语和状态文案。建立词汇表，至少覆盖 Claim、澄清、已说明、证据不足、可信度审计、可提升空间模拟；禁止把 `clarified` 写成“已验证真实”，禁止把 potential delta 写成录用概率。
4. 统一 API 契约：状态 enum、时间格式、分页、错误 envelope、错误码、幂等键和任务进度。前端不再根据自由文本猜测错误类型。
5. 收拢重复代码：路由只负责输入输出，授权、状态迁移、Claim、忠实写回、配额分别进入明确服务；前端将重复请求、状态映射和澄清逻辑收敛到 feature API/hook/util。
6. 盘点临时兼容路径。每一条必须标注调用方、移除条件和截止批次；无测试保护的旧旁路不得永久保留。
7. 建立两条端到端冒烟链路：
   - 候选人：上传 → 忠实建议 → 投递快照 → Claim 回复；
   - 招聘方：岗位 → 申请 → 授权审计 → 澄清 → 邀请。
8. 将当前 lint 的 25 errors、14 warnings 建立基线清单；本批次触及的文件不得新增 lint 问题，PR 7 前清零全局存量。

### 禁止事项

- 不以“大重构”为名改写整个仓库；
- 不批量格式化或覆盖用户未提交改动；
- 不为了减少文件数重新合并授权、状态机和 AI 写回边界；
- 不删除兼容分支，除非先证明没有调用方或完成迁移；
- 不用关闭 ESLint/类型/安全规则制造“整洁”结果。

### 验收

- 同一业务规则只有一个权威实现，路由和页面不再各自复制判断；
- 两条端到端链路通过，后端完整回归无 XFAIL；
- 前后端词汇、状态和错误行为一致；
- 新增代码不引入新的 lint error，现有 lint 债有可追踪清单；
- 输出模块边界图、术语表、兼容路径清单和后续删除计划。

---

## 11. PR 6：一键启动与客户交付

**状态：已完成（2026-07-25）。详见 `PR6_IMPLEMENTATION_AND_VERIFICATION_REPORT.md` 与 `PR6_FINAL_GATE_CLOSURE.md`。**

### 产品决定

- 正式客户：托管 SaaS，只访问一个 HTTPS URL；
- 私有化客户：一条 `docker compose up -d --build`；
- 移动访问：先交付响应式 Web/PWA，支持添加到主屏幕和 Web Push；
- 开发者：根目录统一 `make dev/test/stop` 或跨平台脚本。

当前不开发完整 App Store 客户端。只有在 Web 试点证明面试通知、澄清回复、面试练习和进度提醒属于移动端高频场景后，再建设原生/跨平台 companion app。招聘方候选人对比、可信度审计、岗位管理和简历重编辑继续以 Web 为主。禁止仅用 WebView 包装网站提交商店。

进入 App Store 开发前必须已经具备：

- 可访问的隐私政策；
- 数据最小化和第三方 AI 数据共享说明；
- 用户授权撤回；
- App 内发起账户及关联数据删除；
- 审核用 demo account / demo mode；
- 若使用第三方社交登录，满足 Apple 等价登录服务要求；
- 原生移动价值，而非网站壳。

### Compose 目标

- frontend 多阶段构建并由 Nginx/等价服务托管；
- backend 生产模式，无 `--reload`；
- PostgreSQL、Redis；
- 独立 worker/scheduler；
- 统一入口反向代理 `/api`、`/ws`；
- 健康检查、持久化卷、启动依赖；
- 浏览器只访问一个端口/域名；
- `.env.example` 不含真实密钥；
- 缺少模型 Key 时显示降级状态；
- README 包含 3 分钟启动、停止、升级、备份、恢复和排障。

### 验收

- 新机器仅安装 Docker 即可启动；
- 注册、登录、上传、岗位、投递、澄清基本链路可用；
- 重启后数据保留；
- 不再要求客户分别运行 npm 与 uvicorn；
- 生产配置不暴露数据库、Redis 和 backend 内部端口。

---

## 12. PR 7：工程质量、迁移和扩容

### 前端

- 修完当前 lint errors/warnings，不关闭规则掩盖；
- 修复未定义组件、Hook 依赖、重复请求和派生状态；
- 路由级 lazy loading，降低约 1.43 MB 主包；
- 统一 401/403/402/429、loading/empty/error/retry；
- 关键流程组件测试和 E2E。

### 数据库

- Alembic 替代启动时手写 ALTER；
- `(resume_id, job_id)` 等唯一约束；
- 申请、邀请、反馈、Claim 的约束和索引；
- 数据迁移升级与回滚测试。

### 后台任务和多实例

- 同步 LLM 调用改 Async client 或任务队列；
- 解析、全量匹配、抓取、重建异步化；
- scheduler 独立，避免多 worker 重复任务；
- 进程内 SSE EventBus 迁移 Redis Pub/Sub/Streams；
- 增加超时、重试、幂等、进度和失败恢复。

### CI

- Python lint/format/type check；
- 后端单元/集成测试；
- 前端 lint/test/build；
- E2E；
- 迁移测试；
- dependency/secret scan。

---

### 试点前公平性最低协议

如果匹配分、可信度结果或后续 Potential Score 会影响招聘方排序，PR 7 必须建立最低监控协议：

- 明确系统输出是辅助信息，不允许自动淘汰候选人；
- 按岗位族分别统计分数分布、进入推荐 Top-K 的比例和人工复核结果；
- 在法律允许且具备合规基础时，使用去标识化分组数据评估 selection rate / impact ratio；不能为了公平性评测擅自收集敏感信息；
- 检查学校层级、年龄、性别、地区、语言风格等敏感属性或代理变量是否影响排序；
- 招聘方 `useful`、面试邀请、历史录用只能作为带偏差风险的观察信号，不能直接当“真实能力”标签；
- 记录规则/模型版本，保留人工介入、说明、更正和申诉入口；
- 在试点报告中同时披露样本量、置信区间和已知限制，样本不足时不下结论。

---

## 13. PR 8：Claim Passport MVP

### 研究约束

Claim Passport 采用数据溯源思想：记录谁在何时基于哪些来源生成或修改了 Claim，但不证明 Claim 在现实世界中绝对真实。MVP 不引入区块链、RDF 或高敏感原件存储。

建议正式关系表：

- `resume_claims`：稳定 claim ID、简历/版本、字段路径、原文、当前文本；
- `claim_evidence`：用户说明、指标背景、文档引用、招聘方复核及来源类型；
- `claim_revisions`：改写前后、使用 evidence、模型/提示词/规则版本、忠实度结果；
- `claim_application_links`：投递时 Claim 文本快照、申请和审计状态；
- `claim_events`：不可覆盖的状态迁移与修订历史。

### MVP 状态收敛

不要在 MVP 中将八个业务状态混为一个字段。拆成两层：

**证据语义 `evidence_state`：**

- `supported_by_user_evidence`：有用户提供的来源支持，不等于第三方认证；
- `not_enough_information`：证据不足；
- `conflict_detected`：不同来源存在冲突，仍需人工处理。

**工作流语义 `workflow_state`：**

- `open`；
- `answered`；
- `reviewed`；
- `withdrawn`。

UI 禁止使用“已验证真实”“认证通过”。建议文案为“用户已说明”“有用户证据支持”“招聘方已复核提问”“信息不足”“存在待处理冲突”。`clarified` 只表示用户完成说明，不代表事实被证明。

### 整合

- 体检发现问题时创建/更新 Claim；
- evidence follow-up 写 evidence；
- faithful rewrite 写 revision；
- clarification 使用稳定 claim ID；
- credibility audit 读取 Passport，但不能覆盖用户原始证据；
- 投递保存不可变快照，当前简历修改不污染历史申请；
- 为 PR 9 提供稳定 Claim ID、证据与版本接口。

### 权限与隐私

- 候选人可查看、更正和撤回自己的补充内容；
- 招聘方只看当前申请明确授权的 Claim 快照；
- 不同招聘方不能看到彼此的问题、反馈和无关申请；
- MVP 不保存身份证、工资单等高敏感原件；
- 撤回不能篡改已发生的审计事件，但必须停止后续非必要使用，并按数据保留规则删除或匿名化内容；
- 每次读取敏感 Claim 快照都应受到对象级授权检查。

### 验收

- claim ID 跨体检、改写、澄清、审计保持稳定；
- 每个写回文本可追溯到原文/evidence；
- 无证据不能显示为“已验证”；
- 历史申请快照不受后续修改影响；
- 所有跨租户测试通过；
- 状态文案经测试确认不会把“已说明/已复核”误导为“事实认证”。

---

## 14. PR 9：多路径岗位适配优化与 Potential Score 反事实模拟

### 目标与范围

把当前“增强竞争力 = 反复要求补数字”的单一路径，升级为“先诊断缺口，再让用户选择优化策略”的岗位适配系统。本批次复用 PR 8 的稳定 Claim、Evidence 和 ResumeVersion，不新建一套平行的建议或事实模型。

产品和代码术语使用：

- `TargetRoleProfile` / “目标岗位能力画像”；
- `CompanyWorkContext` / “公司工作语境画像”；
- `EvidencePreferenceProfile` / “证据偏好画像”。

这三者是逻辑边界，不要求 MVP 立即建立三张表；可以先作为 `TargetRoleProfile` 的版本化子对象，避免再次制造重复画像模型。只有访问控制、更新频率或生命周期确实不同，才在后续迁移中拆表。

旧界面中的“大公司偏好画像”可保留兼容读取，但新接口、数据库字段和 UI 不得把历史员工特征称为录用偏好。员工学校、年龄、性别、籍贯、现公司等人口或代理属性不得进入 action 生成和评分。

保留兼容字段，但新增：

- `current_score`；
- `potential_score`；
- `potential_delta`；
- `confidence`（必须有可复现定义）；
- `assumptions`；
- 结构化 `actions`。

Action 分类：

- `evidence_completion`：事实已发生，只需真实证据；
- `resume_reframing`：忠实重组已有内容；
- `skill_learning`：需要真实学习；
- `experience_building`：需要未来项目/经历；
- `preference_change`：用户主动调整地点/薪资/方向；
- `hard_constraint`：短期不可改变。

### 14.1 缺口分类契约

新增稳定枚举，不允许前后端用自由文本自行猜测：

- `presentation_gap`；
- `relevance_gap`；
- `evidence_gap`；
- `differentiation_gap`；
- `capability_gap`；
- `credibility_risk`；
- `career_narrative_gap`；
- `hard_constraint`。

分类规则必须服务端权威执行。`evidence_gap` 只能表示当前未观察到足够证据，不能自动转换成 `capability_gap`；`credibility_risk` 只能进入澄清或冲突处理，不能通过润色消除；`hard_constraint` 不产生可直接应用的简历 patch。

### 14.2 可选择的优化策略

策略枚举至少包含：

- `relevance_alignment`；
- `role_clarity`；
- `method_and_tradeoff`；
- `scope_and_complexity`；
- `outcome_expression`；
- `quantification`（`outcome_expression` 的可单独统计子类型）；
- `evidence_strengthening`；
- `career_narrative`；
- `portfolio_or_work_sample`；
- `skill_or_experience_building`；
- `constraint_acknowledgement`。

生成规则：

1. 每个 issue 先分类，再筛选合法策略；不得先生成文案再倒推类型。
2. 只要语义允许，每个 issue 返回 2–4 个实质不同的选项以及一个可解释的 `recommended_strategy_id`。
3. `quantification` 不是默认策略。只有存在服务端可追溯数字证据时 `can_apply_now=true`；否则只能创建证据问题，不能生成可应用占位 patch。
4. 没有数字时仍可选择职责边界、方法/权衡、复杂度、岗位相关性、作品证据或定性结果，但同样不得添加原证据不蕴含的事实。
5. `capability_gap` 只生成学习、练习、作品或项目计划；完成并获得新证据前不得提升 current score。
6. `hard_constraint` 只生成确认、替代岗位或长期路径，不承诺通过文字解决。
7. 策略排序考虑岗位要求重要度、缺口严重度、可行动性、证据充分度、用户成本和幻觉风险；LLM 不直接给最终优先级、delta 或 confidence。

### 14.3 API 数据契约

每个 issue 至少返回：

```json
{
  "issue_id": "uuid",
  "issue_type": "differentiation_gap",
  "target_requirement_id": "job-requirement-id",
  "claim_ids": ["claim-id"],
  "diagnosis": "当前内容描述了任务，但未体现本人职责和方法选择",
  "source_refs": ["jd-source-id", "claim-id"],
  "strategy_options": [
    {
      "strategy_id": "uuid",
      "strategy": "role_clarity",
      "title": "澄清本人职责",
      "why": "岗位要求独立负责相关任务",
      "requires_evidence": true,
      "can_apply_now": false,
      "next_action": "open_evidence_followup",
      "affected_dimensions": ["relevance", "credibility"],
      "time_horizon": "immediate",
      "user_cost": "low",
      "estimated_delta": 0.0
    }
  ],
  "recommended_strategy_id": "uuid"
}
```

还必须记录：

- taxonomy、JD source、scoring、rule、prompt 和 model 版本；
- `expression_delta`、`evidence_delta`、`capability_delta`；
- 证据快照和模拟假设；
- 用户查看、切换、拒绝、采纳和完成策略的事件。

`estimated_delta=0` 可以表示需要先补证据，不能为了让建议看起来有价值而预先增加 current score。兼容的 `potential_delta` 可以保留，但必须由实际评分器重算。

### 14.4 决策流程

实现顺序固定为：

1. 解析并版本化公司官方 JD；
2. 使用 ESCO/O*NET 和本地职业 crosswalk 标准化任务/技能；
3. 从 ResumeVersion、Claim Passport 和已授权 InterviewAnswer 读取事实与证据；
4. 对每个重要 requirement 生成 issue 并分类；
5. 使用确定性 eligibility rules 过滤不合法策略；
6. 对合法策略生成受约束说明、问题、patch 草案或成长行动；
7. 由服务端忠实度与证据门禁决定 `can_apply_now`；
8. 用户选择策略；
9. 构造完整反事实输入并用同一评分器重算；
10. 用户确认后生成新 ResumeVersion、Evidence follow-up 或 Capability action，三者不得混写。

### 14.5 前端

将建议分成四栏：

- “现在可以优化”；
- “需要补充证据”；
- “需要真实提升”；
- “硬门槛”。

每个 issue 以策略卡展示：

- 为什么出现；
- 对应 JD requirement 与来源；
- 推荐策略及其他选项；
- 是否可写回、需要什么证据；
- 影响的是表达、证据还是能力；
- 模型内 delta、置信度、成本和时间范围。

按钮必须按动作区分为“预览改写”“回答问题”“添加证据”“创建成长计划”“查看替代岗位”，不可写回的内容不得显示“采纳到简历”。用户切换策略后重新模拟，不自动修改简历。

每个 action 包含：时间范围、可行性、是否需证据、影响维度、预计 delta、原因、下一步。

规则：

1. delta 必须通过现有评分函数对反事实输入重新计算，不能让 LLM 随口打分；
2. 多动作组合重新评分，不能简单相加；
3. 无证据只能提升模拟 potential，不能提升 current 或写回简历；
4. 与 Claim Passport 联动，需要证据的 action 直接进入对应 Claim；
5. 展示“如果……那么……”与置信度，明确它只是当前模型内的相对变化，不是录用概率；
6. 固定至少 20 组简历/JD 回归样本；
7. 记录评分规则版本，使结果可复现；
8. `hard_constraint` 永不承诺可以通过文字修改解决；
9. 不得把年龄、性别、学校层级等敏感/不可行动特征变成改进建议；
10. `confidence` 由 JD 解析完整性、规则覆盖、样本充分度和模拟稳定性计算，禁止由 LLM 自报；
11. 招聘结果数据没有完成校准前，不得把 delta 描述成面试或录用概率；
12. 产品名称优先使用“可提升空间模拟/匹配改进模拟”，避免将模型分数包装成个人潜力。
13. “补充数字”不得成为所有 issue 的共同兜底；当数字不适用或无来源时必须有非量化路径或明确说明当前无合法改写。

前端实现可勾选的提升模拟器，按“立即可做/中期成长/硬门槛”分组，并固定显示“模型内模拟，不代表录用承诺”。

### delta 校准与虚假补救评测

PR 9 验收不能只有边界测试，还必须包含：

- **有效性**：应用 action 后用同一评分函数重算，delta 与结果一致；
- **忠实性**：无证据动作不改变 current score 或简历；
- **可行动性**：用户确实能执行，成本和时间范围明确；
- **稳定性**：同一规则版本重复计算一致，小幅无关输入变化不造成巨大 delta；
- **组合一致性**：组合动作重新模拟，避免重复加分；
- **校准**：按 delta 区间比较后续真实行为结果，只能在样本充分后报告关系；
- **公平性**：不同群体获得相同模型提升所需的成本和可行性差异；
- **虚假承诺用例**：完成建议但模型外结果未改变时，UI 仍不能显示“保证面试/录用”；
- **人工评审**：至少由候选人和招聘从业者抽检动作是否现实、清晰且无冒犯。
- **缺口分类**：人工标注固定集评估 issue type，重点检查 evidence gap 被误判为 capability gap；
- **策略多样性**：适用样本至少有两条实质不同策略，禁止只更换标题或同义改写；
- **量化门禁**：没有数字来源的样本中，可应用 quantification 数量必须为 0；
- **跨岗位样本**：固定集包含技术、产品、运营、设计、研究、管理和应届项目，且包含本来就不适合量化的经历；
- **路径正确性**：表达优化、证据补充、能力成长和硬门槛分别进入正确工作流；
- **来源可追溯**：公司/岗位画像和每个策略都能回指官方 JD、taxonomy、Claim/answer 与版本；
- **产品指标**：记录量化建议占比、策略重复率、各策略查看/选择/采纳率、证据完成率和能力行动完成率。

### PR 9 完成门禁

- 旧的“总是补数字”回归样本全部通过；
- 对可改写问题能够返回非量化策略，对不可改写问题不会伪造 patch；
- 后端拒绝客户端把不可应用策略篡改为可应用；
- 前端四栏、策略切换、错误态、空状态、刷新恢复和移动端布局通过；
- 相同版本输入输出可复现，组合 action 不重复计分；
- 需求追踪矩阵覆盖本节 14.1–14.5，未达到任一门禁只能报告“部分完成”。

---

## 15. 下一条可直接发给 Cursor 的命令

```text
完整阅读 CURSOR_PR0_PR3_CLOSURE_SPEC.md、PR3_IMPLEMENTATION_SPEC.md、CURSOR_DEFINITION_OF_DONE.md、CURSOR_EXECUTION_BACKLOG.md、CURSOR_REMEDIATION_PLAN.md 和当前 git status。
PR 0、PR 1、PR 2 的原定向回归曾通过，PR 3 也已有部分实现；这些结果只代表旧测试通过，不代表 CURSOR_PR0_PR3_CLOSURE_SPEC.md 的五个阻断项已经关闭。
仓库已有部分 PR0–PR3 实现，不得重新平行实现。
本轮只执行 PR0–PR3 收口：关闭 CURSOR_PR0_PR3_CLOSURE_SPEC.md 的五个阻断项，其中 PR3 按 PR3_IMPLEMENTATION_SPEC.md 实现；不执行 PR4 或后续任务。
第一步只能做只读差距审计：逐项输出两个规格的“已满足/部分满足/未满足”需求追踪矩阵、证据文件/行号、现有错误测试语义、授权链、数据迁移与并发风险。完成矩阵后再编码。
必须重点修正：人工关闭不能显示 clarified；终态不能回退；状态变化只有一个权威迁移图；initial submission snapshot 永不覆盖；自动路径不换 resume；招聘方已查看或产生业务活动后禁止显式覆盖；回复/关闭/邀请事务一致；并发不能丢 Claim 更新。
必须先新增或修正失败测试，再做最小实现。不得削弱 Findings 断言，不得用 fixture 直接制造最终状态代替业务动作。
保留全部已有暂存、未暂存和未跟踪改动；禁止 reset、checkout 或覆盖用户改动。
完成后严格使用 CURSOR_DEFINITION_OF_DONE 的报告格式；任一 PR0–PR3 收口门禁未通过只能报告“部分完成”。
```

PR0–PR3 收口验收以 `CURSOR_PR0_PR3_CLOSURE_SPEC.md` 第 16 节和 `PR3_IMPLEMENTATION_SPEC.md` 第 10 节共同为准；`baseline 6 passed` 只是其中一项，不能替代完整验收。不要用“按文档全部完成”作为一次性提示。

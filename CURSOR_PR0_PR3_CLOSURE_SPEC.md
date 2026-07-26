# PR0–PR3 收口整改规格与验收清单

> 执行对象：Cursor  
> 执行范围：仅收口 PR0、PR1、PR2、PR3 遗留问题  
> 当前结论：现有实现虽然通过部分自动化测试，但仍存在授权绕过、无证据写回、状态语义错误、快照覆盖和执行过程不可复现等问题，暂不能进入 PR4  
> 本文优先级：如本文与旧的“已完成”描述冲突，以本文列出的阻断项和验收标准为准；不得仅根据旧文档中的完成状态跳过核验

---

## 0. 本轮目标

本轮不是继续增加产品功能，而是把 PR0–PR3 修到以下状态：

1. 招聘方无法通过自行制造申请关系访问任意候选人简历或可信度审计；
2. 任何写入简历的新事实都有服务端可验证的来源；
3. `clarified` 只表示候选人确实完成了所需回复；
4. 申请状态由唯一、明确的迁移规则控制；
5. 投递时简历快照永久保留，后续更换不会覆盖历史；
6. 自动化测试能够证明上述安全语义，而不只是证明接口返回成功；
7. 本轮改动可以独立审查、复现和回滚；
8. 在全部阻断项关闭前，不开始 PR4、PR5 或新的 UI/AI 功能。

完成本轮不等于产品可以正式处理真实客户数据。PR4–PR7 中的全接口权限、上传、认证、配额、部署和质量门禁仍然存在。

---

## 1. 执行前必须阅读

开始前完整阅读：

- `CURSOR_PR0_PR3_CLOSURE_SPEC.md`；
- `CURSOR_EXECUTION_BACKLOG.md`；
- `CURSOR_REMEDIATION_PLAN.md`；
- `CURSOR_DEFINITION_OF_DONE.md`；
- `PR3_IMPLEMENTATION_SPEC.md`（PR3 文件/函数/迁移/测试细化规格）；
- `AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`；
- 当前 `git status --short`；
- 当前 staged、unstaged、untracked 文件；
- 本文涉及的后端、前端和测试代码。

文档优先级：

1. 本文定义 PR0–PR3 必须关闭的安全与数据阻断范围；
2. `PR3_IMPLEMENTATION_SPEC.md` 将本文第 6–8 节细化为确定的 PR3 产品语义和实施路径；
3. `CURSOR_DEFINITION_OF_DONE.md` 定义所有批次的执行和完成证据；
4. 若仍有冲突，采用更严格、不会把未回复表示为已澄清、不会扩大授权、不会覆盖历史快照的规则；无法判断时停止并请求用户决定。

重点文件至少包括：

- `backend/app/application_routes.py`
- `backend/app/application_authz.py`
- `backend/app/application_state.py`
- `backend/app/application_status.py`
- `backend/app/claim_threads.py`
- `backend/app/invitation_routes.py`
- `backend/app/main.py`
- `backend/app/models_db.py`
- `backend/app/db_schema.py`
- `backend/app/resume_suggestions.py`
- `backend/app/resume_suggestion_store.py`
- `backend/tests/conftest.py`
- `backend/tests/test_security_skeleton.py`
- `backend/tests/test_security_findings_baseline.py`
- `backend/tests/test_pr1_audit_auth.py`
- `backend/tests/test_pr2_faithful_writeback.py`
- `backend/tests/test_pr3_state_machine.py`
- `backend/scripts/pr3_manual_accept.py`
- `scripts/pr3_manual_accept.sh`
- `frontend/src/constants/applicationStatus.js`
- 与申请状态、澄清、邀请、简历建议相关的前端组件。

---

## 2. 工作区保护规则

当前工作区不是干净分支，已有大量 staged、unstaged 和 untracked 内容。所有现存改动都视为用户资产。

### 2.1 禁止操作

禁止执行：

- `git reset`；
- `git checkout -- <file>`；
- `git restore <file>`；
- `git clean`；
- 自动 `git stash`；
- 覆盖整个文件以替代小范围修改；
- 格式化无关目录；
- 批量重命名无关文件；
- 修改或删除用户已有 staged 内容；
- 为了制造干净 diff 而丢弃现有改动；
- 未经用户明确要求自行提交、推送或创建 PR。

### 2.2 修改要求

1. 修改前记录目标文件的 staged/unstaged 状态。
2. 只修改本轮直接涉及的文件。
3. 如果目标文件同时存在用户改动，必须做最小局部修改。
4. 不得把无关变化混入本轮结果。
5. 完成后逐文件检查 diff，确认没有覆盖任务开始前的逻辑。
6. 如果无法区分现有改动与本轮改动，停止并报告，不得猜测删除。

### 2.3 开始前固定输出

修改代码前先向用户输出：

- 本轮处理的阻断项；
- 预计修改文件；
- 每个文件为什么需要修改；
- 数据结构或迁移影响；
- 旧数据兼容风险；
- 测试计划；
- 如何保护当前混合工作区；
- 明确声明本轮不执行 PR4 及后续任务。

---

## 3. 不允许使用的“修复方式”

以下方式即使让测试通过，也视为失败：

1. 把严格断言改成更宽泛的状态码集合；
2. 删除、跳过、`xfail` 或注释掉失败测试；
3. 只修前端按钮，不做后端强制校验；
4. 信任客户端传来的：
   - `user_id`
   - `employer_id`
   - `candidate_id`
   - `role`
   - `evidence_completed`
   - `requires_evidence`
   - `claim_id` 的资源归属
   - suggestion 的 action、section、index、field；
5. 只检查“文本不是占位符”就认为它是真实证据；
6. 把 MatchResult、招聘方主动邀请或招聘方主动创建的申请直接当成候选人授权；
7. 为了兼容旧数据而静默使用当前简历冒充投递快照；
8. 用 `try/except Exception: pass` 隐藏核心事务错误；
9. 在数据库提交前向外宣称业务动作成功；
10. 增加未记录、无限期保留的后门参数；
11. 在没有迁移方案时直接修改生产数据含义；
12. 提前把任务文档状态改成“已完成”。

---

## 4. 阻断项一：关闭任意简历审计授权绕过

### 4.1 已确认问题

当前审计接口主要根据以下关系授权：

- 当前招聘方拥有岗位；
- 存在 `job_id + resume_id + employer_id` 对应的 `JobApplication`。

但人才池澄清和邀请路径可以在没有候选人主动申请、没有候选人可见性授权时，由招聘方针对任意存在的 `resume_id` 自动创建 `JobApplication`。

这会形成授权绕过链：

```text
招聘方拥有自己的岗位
    ↓
猜测或获得其他候选人的 resume_id
    ↓
调用人才池澄清或邀请
    ↓
系统自动创建 JobApplication
    ↓
审计授权看到“存在申请”
    ↓
招聘方获得任意简历的可信度审计
```

因此，“存在申请”只有在申请来源可信时才能作为授权依据。

### 4.2 本轮安全规则

在候选人可见性/授权模型完成前，采用保守规则：

1. 只有候选人主动创建的真实投递可以授权招聘方访问该岗位下的申请简历；
2. MatchResult 不构成授权；
3. 招聘方自行创建的 sourced/invited 记录不构成简历审计授权；
4. 招聘方不能仅凭 `resume_id` 创建可读取简历内容的申请；
5. 招聘方针对无申请简历发起澄清或邀请时，返回统一的 404 或项目选定的防枚举响应；
6. 响应不得泄露：
   - 简历是否存在；
   - 候选人身份；
   - 简历解析状态；
   - 是否属于其他租户；
7. 后端不能依赖前端隐藏人才池按钮；
8. 如果现有产品必须保留主动邀约，需建立最小、显式、可审计的授权记录，至少包含：
   - 候选人 ID；
   - 允许可见的范围；
   - 授权对象或组织；
   - 授权时间；
   - 过期时间；
   - 撤回状态；
   - 授权来源；
   - 服务端验证逻辑。

本轮优先采用“无明确授权则拒绝”，不要顺带实现完整人才公开市场。

### 4.3 申请来源要求

如果保留自动创建的申请型记录，必须明确区分来源，例如：

- `candidate_applied`
- `candidate_consented`
- `employer_sourced`
- `employer_invited`
- `legacy_unknown`

必须满足：

1. 只有安全白名单来源可以授权审计；
2. 来源由服务端写入，客户端不能指定；
3. 旧数据不能默认视为 `candidate_applied`；
4. `legacy_unknown` 默认不授权敏感审计；
5. 审计 helper 必须检查来源或有效授权，而不是只检查记录存在。

如果本轮不增加来源字段，则必须禁止无申请自动创建路径，避免产生模糊授权。

### 4.4 必须新增的自动化测试

至少覆盖：

1. employer A 使用自己的 job + candidate B 的任意 resume 发起澄清失败；
2. employer A 使用自己的 job + candidate B 的任意 resume 发邀请失败；
3. 上述失败后数据库没有新增 JobApplication；
4. 上述失败后数据库没有新增 Invitation、Message、Claim thread；
5. 上述失败后可信度审计仍为 404；
6. 只有 MatchResult、没有真实申请时，澄清、邀请和审计均失败；
7. candidate B 主动向 employer A 的 job 投递后：
   - employer A 可以查看该申请；
   - employer A 可以发起澄清；
   - employer A 可以发送邀请；
   - employer A 可以审计投递快照；
8. employer B 不能利用 employer A 的真实申请访问简历；
9. 不存在 resume ID 与他人 resume ID 返回一致的防枚举语义；
10. 客户端传入虚假 application_id 不能改变授权结果。

### 4.5 验收条件

- 无授权路径无法创建可提升权限的关系；
- 合法候选人投递流程不受破坏；
- 测试证明数据库无副作用；
- 权限 helper 有单一明确的授权依据；
- 不再以“JobApplication 存在”作为无条件授权。

---

## 5. 阻断项二：忠实写回必须使用服务端证据

### 5.1 已确认问题

当前实现存在以下风险：

1. `apply-suggestion` 可以不传 `suggestion_id`，直接提交任意 patch；
2. 客户端可以传 `evidence_completed=true`；
3. 一段非空、非占位文本会被当作真实证据；
4. 后端没有验证 evidence/clarification 是否：
   - 存在；
   - 已完成；
   - 属于当前用户；
   - 属于当前简历；
   - 属于当前 Claim；
   - 对应当前目标字段；
5. 客户端可以尝试修改 action、section、index、field；
6. 没有服务端证据引用时，攻击者仍可能写入虚构数字、角色或结果。

### 5.2 服务端真相源

写回必须以数据库中的服务端对象为准：

```text
ResumeSuggestion
    ↓
目标 resume / claim / field
    ↓
Evidence 或 Clarification Answer
    ↓
服务端确认完成状态
    ↓
受约束生成或用户确认文本
    ↓
apply
```

客户端只能发出“请求应用哪条建议”和允许编辑的候选文本，不能声明证据已经完成。

### 5.3 apply 接口强制规则

1. `suggestion_id` 必填；如保留 `suggestion_key`，它必须在当前 resume 内唯一并由服务端查询；
2. suggestion 必须：
   - 存在；
   - 属于当前 resume；
   - resume 属于当前登录候选人；
   - 状态为 pending/ready 等允许状态；
3. suggestion 的以下字段以数据库为准：
   - action；
   - section；
   - index；
   - field；
   - field_path；
   - claim_id；
   - requires_evidence；
   - needs_followup；
4. 客户端不得改变目标字段；
5. `requires_evidence=true` 时必须加载服务端 evidence/clarification；
6. 服务端 evidence 至少验证：
   - 所有者；
   - resume ID；
   - claim ID；
   - 完成状态；
   - 未撤回；
   - 未过期或未失效；
7. 不能只验证“文本像证据”；
8. 对数字、比例、金额、规模、职位、技术、证书、结果等新事实，必须能回指具体来源；
9. apply 成功后记录：
   - suggestion ID；
   - evidence/answer ID；
   - 原字段值；
   - 新字段值；
   - actor ID；
   - 时间；
   - 生成/规则版本；
10. apply 失败时：
    - Resume 不变；
    - suggestion 状态不变；
    - evidence 状态不变；
    - 不刷新匹配；
    - 不记录 applied usage。

### 5.4 允许的内容类型

可以区分：

1. `format_only`：仅格式、标点、排序，不增加事实；
2. `faithful_reframe`：只重组已有原文；
3. `evidence_backed_addition`：加入用户已经提供并绑定的证据；
4. `question_only`：事实不足，只生成问题，不可 apply；
5. `simulation_only`：只做预览或潜力模拟，不写回 current resume。

任何建议必须明确属于其中一种。`question_only` 和 `simulation_only` 不得进入写回路径。

### 5.5 preview 规则

preview 可以展示假设效果，但必须：

- 明确标记为假设；
- 不改变 Resume；
- 不改变 current score；
- 不把预览文本变成可直接 apply 的服务端 ready suggestion；
- 不将客户端任意文本登记成 evidence；
- 返回是否满足写回条件以及缺少的证据。

### 5.6 必须新增的自动化测试

至少覆盖：

1. 无 suggestion ID 的任意 patch 被拒绝；
2. 不存在 suggestion ID 被拒绝；
3. suggestion 属于其他 resume 被拒绝；
4. suggestion 属于其他用户被拒绝；
5. 客户端伪造 `evidence_completed=true` 被拒绝；
6. 客户端将 append 改为 fill_field 被拒绝；
7. 客户端修改 section/index/field 被拒绝；
8. 无服务端 evidence 时提交“收入提升 300%”被拒绝；
9. 无服务端 evidence 时提交“技术负责人/主导研发”被拒绝；
10. evidence 属于其他 Claim 时被拒绝；
11. evidence 属于其他 resume 时被拒绝；
12. evidence 已撤回/未完成时被拒绝；
13. 合法 evidence 绑定后允许写回；
14. 合法写回记录 evidence ID 和原/新值；
15. 失败后 Resume 和 suggestion 状态不变；
16. 重放同一 apply 请求不会重复追加文本；
17. 并发 apply 不会重复写回。

### 5.7 验收条件

- 客户端不能自行声明事实真实；
- 所有新增事实都有服务端来源；
- 无 suggestion 的任意写回被关闭；
- action 和目标字段完全由服务端控制；
- 失败路径没有部分提交；
- 回归测试包含恶意客户端，而不只覆盖正常 UI。

---

## 6. 阻断项三：人工关闭不能等于候选人已澄清

### 6.1 状态语义

`clarified` 必须严格表示：

- 系统曾创建一个或多个有效 Claim 澄清请求；
- 所有需要回复的开放 Claim 都由候选人提交了有效回复；
- 每条回复绑定到正确的 Claim；
- 系统没有把招聘方关闭、超时、撤销或跳过视为候选人回复。

以下情况都不能产生 `clarified`：

- 招聘方人工关闭；
- 请求超时；
- 招聘方撤销问题；
- 系统删除问题；
- 没有 Claim；
- 仅发送普通消息；
- 候选人回复了其他 Claim；
- 空白或无效回复；
- 前端直接 PATCH 状态。

### 6.2 推荐设计

Claim thread 状态建议至少区分：

- `open`
- `answered`
- `reviewed`
- `closed_by_employer`
- `withdrawn`
- `expired`

本轮申请级状态采用方案 A，不再保留二选一：

#### 已选方案：新增明确申请状态

- `clarification_closed`
- UI 文案：“招聘方已关闭澄清，候选人未完成全部回复”

#### 未采用方案：保持招聘流程状态

- 回到 `viewed` 或保持现有非 clarified 状态；
- 在 `pipeline_meta.clarification_outcome` 中保存：
  - `closed_by_employer`
  - reason
  - actor
  - time

方案 B 仅保留为决策记录，不得实现。本轮新增 `clarification_closed`；关闭原因必填。具体枚举、迁移、接口和前端文案以 `PR3_IMPLEMENTATION_SPEC.md` 为准。

### 6.3 重算规则

澄清重算必须使用明确条件：

```text
存在 open
  → needs_clarification

没有 open，且所有 required Claim 都是 answered/reviewed
  → clarified

没有 open，但至少一个 required Claim 是 closed_by_employer/expired/withdrawn
  → clarification_closed

没有任何 Claim
  → 不改变为 needs_clarification/clarified
```

### 6.4 人工关闭留痕

必须记录：

- closed_by；
- close_reason；
- closed_at；
- 原 thread 状态；
- 是否由招聘方关闭；
- 受影响 Claim ID；
- 申请级 outcome；
- status history 的明确 source。

reason 必填；trim 后为空或超过接口限制时拒绝，且不能用默认文案冒充用户填写的关闭原因。

### 6.5 必须新增/修改的测试

1. 人工关闭所有 Claim 后不是 `clarified`；
2. UI/API label 不显示“已澄清”；
3. closed Claim 没有 response_message_id；
4. closed Claim 不设置 answered_at；
5. 人工关闭记录 actor、reason、time；
6. 候选人不能调用人工关闭；
7. 其他招聘方不能关闭；
8. 没有开放 Claim 时关闭失败且无副作用；
9. 一个 answered + 一个 employer closed 不得变成 clarified；
10. 所有 required Claim 都 answered 后才是 clarified；
11. reviewed 只能建立在 answered 基础上；
12. 删除现有“人工关闭后 status=clarified”的错误断言。

---

## 7. 阻断项四：实现唯一状态迁移表

### 7.1 已确认问题

当前实现主要校验目标状态是否允许，但没有完整校验：

```text
当前状态 → 目标状态
```

因此可能出现：

- rejected → accepted；
- accepted → viewed；
- rejected → viewed；
- interview_invited → submitted；
- 终态被通用 PATCH 重新打开。

定义了常量但未使用，不等于建立了状态机。

### 7.2 单一真相源

状态规则只能有一个权威模块。不得同时存在：

- `EMPLOYER_SETTABLE_STATUSES`
- 另一套 `EMPLOYER_PATCHABLE_STATUSES`
- 路由内硬编码集合
- 前端另一套不一致集合

推荐由领域服务提供：

- 合法状态集合；
- 合法迁移表；
- 每种迁移允许的业务动作；
- actor/role 限制；
- 终态规则；
- 状态历史记录。

前端常量只用于显示，不能成为授权依据。

### 7.3 推荐迁移模型

具体产品规则可在实现前说明，但至少满足：

| 当前状态 | 允许动作 | 目标状态 |
|---|---|---|
| submitted | employer_view | viewed |
| submitted/viewed | create_claim_request | needs_clarification |
| needs_clarification | candidate_answers_some | needs_clarification |
| needs_clarification | candidate_answers_all | clarified |
| needs_clarification | employer_closes | clarification_closed |
| submitted/viewed/clarified | create_invitation | interview_invited |
| 合法非终态 | employer_rejects | rejected |
| 合法非终态 | employer_accepts | accepted |
| accepted/rejected | 默认无通用迁移 | 保持终态 |

如果允许撤销录用或恢复拒绝，必须是单独业务动作，记录原因和审计信息，不能复用通用 PATCH。

### 7.4 领域服务要求

所有申请状态变化必须经过同一服务：

- 通用 status PATCH；
- 自动标记 viewed；
- 创建 Claim；
- 回复 Claim；
- 人工关闭 Claim；
- 创建邀请；
- 接受/拒绝邀请；
- 录用/拒绝。

服务必须：

1. 验证当前状态；
2. 验证目标状态；
3. 验证业务动作；
4. 验证 actor role；
5. 验证必要领域条件；
6. 成功时写 status history；
7. 失败时不写 history；
8. 同状态幂等请求不能制造重复 history；
9. history 使用 UTC 时间；
10. history 至少包含 from/to/action/source/actor/reason。

### 7.5 事务规则

状态变化与产生该状态的业务记录必须处于同一事务：

- 创建 Claim message/thread 成功，状态才变为 needs_clarification；
- 所有回复成功落库，状态才变为 clarified；
- Invitation 成功落库，状态才变为 interview_invited；
- 任一数据库写入失败，全部回滚；
- 邮件和事件推送失败不应回滚已经成功的核心业务，但必须记录可重试状态；
- 不得在 commit 前发布“已成功”事件。

### 7.6 必须新增的自动化测试

1. submitted → viewed 成功；
2. viewed → accepted/rejected 按产品规则成功；
3. rejected → accepted 失败；
4. accepted → rejected 失败；
5. accepted/rejected → viewed 失败；
6. candidate 不能通用 PATCH 任意状态；
7. employer 不能通用 PATCH derived status；
8. 无 Claim 不能进入 needs_clarification；
9. 创建 Claim 事务失败时状态保持不变；
10. 回复部分 Claim 仍为 needs_clarification；
11. 回复全部 Claim 才为 clarified；
12. 创建 Invitation 失败时状态保持不变；
13. 创建 Invitation 成功后才为 interview_invited；
14. 同状态幂等操作不重复写 history；
15. 非法迁移不写 history；
16. 并发状态更新不会发生丢失更新；必要时使用行锁或乐观版本。

---

## 8. 阻断项五：投递快照和版本历史不可变

### 8.1 已确认问题

当前显式换简历会：

1. 把旧快照放入 `previous_snapshot`；
2. 用新简历覆盖 `pipeline_meta.resume_snapshot`；
3. 更新 `application.resume_id`；
4. 审计接口随后读取新的 `resume_snapshot`。

这会导致“投递时快照”不再是投递时内容。

### 8.2 不可变原则

必须区分：

- 原始投递快照；
- 当前申请使用版本；
- 后续主动更换版本；
- 已生成的审计记录引用版本。

`initial_submission_snapshot` 一旦创建不得覆盖。

### 8.3 推荐数据结构

优先使用独立表，例如：

```text
ApplicationResumeVersion
  id
  application_id
  resume_id
  version_number
  snapshot_json
  snapshot_hash
  source
  actor_id
  reason
  created_at
  supersedes_version_id
```

`JobApplication` 可保存：

- `initial_resume_version_id`
- `current_resume_version_id`

如果本轮为了控制范围继续使用 `pipeline_meta`，至少使用：

```json
{
  "initial_resume_snapshot": {},
  "current_resume_version_id": "v2",
  "resume_versions": [
    {
      "version_id": "v1",
      "resume_id": "r1",
      "snapshot_json": {},
      "snapshot_hash": "...",
      "source": "candidate_applied",
      "actor_id": "...",
      "created_at": "..."
    },
    {
      "version_id": "v2",
      "resume_id": "r2",
      "snapshot_json": {},
      "snapshot_hash": "...",
      "source": "candidate_replaced",
      "actor_id": "...",
      "reason": "...",
      "created_at": "..."
    }
  ]
}
```

不得继续用一个可覆盖的 `resume_snapshot` 同时表达“初始”和“当前”。

### 8.4 快照内容

快照应至少包含：

- resume ID；
- parsed JSON 深拷贝；
- 必要时的脱敏 raw text/hash；
- captured_at；
- actor/source；
- schema version；
- 内容 hash。

快照必须在数据库事务中持久化，不能仅持有对可变 Python dict 的引用。

### 8.5 更换简历规则

1. 只有候选人本人可以更换；
2. 必须显式确认；
3. 新 resume 必须属于候选人；
4. 记录原因、actor 和时间；
5. 初始快照保持不变；
6. 创建新的版本记录；
7. 不修改历史 AuditRecord 的版本指向；
8. 招聘方已经看到的历史内容仍可审计；
9. 当前版本和初始版本在 API 中明确区分；
10. 如果业务不允许投递后更换，应直接拒绝，而不是半实现版本历史。

### 8.6 旧数据兼容

旧申请可能没有快照。禁止：

- 把当前 Resume 内容静默复制成“历史投递快照”并声称准确；
- 默认把旧数据标记成已验证历史版本。

允许的策略：

1. 标记 `snapshot_status=legacy_missing`；
2. 审计响应明确说明“无可靠投递时快照”；
3. 从可证明的历史来源回填；
4. 只有能够证明内容版本时才建立回填快照；
5. 迁移必须幂等；
6. 提供回滚方式；
7. 迁移前统计受影响记录数量；
8. 不删除旧字段，直到兼容验证完成。

### 8.7 审计规则

审计接口必须明确指定审计对象：

- 初始投递版本；
- 当前申请版本；
- 某个历史版本。

默认建议审计初始投递版本。响应中返回：

- application ID；
- application resume version ID；
- snapshot captured time；
- snapshot source；
- snapshot status；
- 是否 legacy；
- audit record ID。

AuditRecord 应引用不可变版本，而不是仅引用可能变化的 Resume ID。

### 8.8 必须新增的自动化测试

1. 投递后修改原 Resume.parsed_json，初始快照不变；
2. 审计初始申请读取初始快照；
3. 显式换简历后初始快照不变；
4. 更换后创建新版本；
5. current version 指向新版本；
6. 旧 AuditRecord 仍引用旧版本；
7. 新审计明确选择目标版本；
8. 其他候选人不能替换；
9. 招聘方不能替换；
10. 无 confirm 不产生版本；
11. 事务失败不产生半条版本记录；
12. legacy missing 不冒充可靠快照；
13. 迁移重复执行结果一致；
14. 快照 hash 在内容不变时稳定；
15. invitation/clarification 使用 application 当前允许版本，但不覆盖初始版本。

---

## 9. PR0 测试基线补强

现有测试基础可继续使用，但必须补齐其声明与实际覆盖的差距。

### 9.1 数据库隔离

测试必须：

1. 默认只使用明确测试数据库；
2. PostgreSQL 数据库名必须包含安全测试标识；
3. SQLite 必须位于测试目录；
4. 拒绝连接开发/生产数据库；
5. 测试开始前和结束后都保证隔离；
6. 上次异常中断留下的数据不能导致本次夹具冲突；
7. 不依赖测试执行顺序；
8. 并行执行时不共享会冲突的数据。

### 9.2 权限矩阵

至少建立以下矩阵：

| 资源 | candidate A | candidate B | employer A | employer B | admin | 未登录 |
|---|---|---|---|---|---|---|
| A 的简历 | owner | deny | 仅合法申请范围 | deny | 按明确规则 | deny |
| B 的岗位 | public/限定字段 | public/限定字段 | deny write | owner | 按明确规则 | 仅公开字段 |
| A 的申请 | owner | deny | 对应岗位 owner | deny | 按明确规则 | deny |
| A 的消息 | participant | deny | participant | deny | 按明确规则 | deny |
| A 的审计 | deny/限定 | deny | owner | deny | 按明确规则 | deny |
| A 的反馈 | deny | deny | owner | deny | 按明确规则 | deny |

不能只断言 fixture 的角色字符串，必须调用真实接口验证角色能力。

### 9.3 IDOR 测试

覆盖读、写、改、删：

- resume；
- job；
- application；
- match；
- invitation；
- message；
- audit；
- feedback；
- suggestion；
- evidence；
- claim thread。

### 9.4 SSE 路由

不得只检查路由表中存在路径。必须至少验证：

1. `/applications/stream/me` 真实请求命中正确 endpoint；
2. 不会被解析为 `application_id=stream`；
3. 未登录请求被拒绝；
4. 登录用户建立流连接时返回正确 content type；
5. `/{application_id}/events` 独立可达；
6. 非 participant 不能订阅申请事件；
7. 测试必须设置超时，不能永久挂起。

---

## 10. PR1 审计反馈完整性补强

### 10.1 finding/claim ID

如果客户端提供 `finding_id` 或 `claim_id`，后端必须确认它属于该 AuditRecord 的允许集合。

禁止：

- 当服务端无法从报告提取 ID 时直接跳过校验；
- 接受客户端自造 ID；
- 接受另一个 AuditRecord 的 ID；
- 接受另一个 application 的 Claim。

如果旧 AuditRecord 没有稳定 ID：

1. 拒绝带任意 ID 的反馈，或
2. 提供明确 legacy feedback 类型，不能伪装为 Claim 级反馈。

### 10.2 幂等与重复

建议实现：

- 唯一键或幂等键；
- 同一 employer 对同一 audit/finding 的重复请求更新而不是无限插入；
- 并发请求不会产生重复训练标签；
- 客户端不能覆盖 employer ID；
- finding snapshot 只保存允许的脱敏结构。

### 10.3 测试

至少新增：

1. AuditRecord 无稳定 IDs 时提交伪造 finding ID 被拒绝；
2. 其他 AuditRecord 的 finding ID 被拒绝；
3. 合法 finding ID 成功；
4. 重复反馈符合幂等规则；
5. 并发重复请求不产生重复记录。

---

## 11. PR3 人工验收脚本安全

当前人工验收脚本会读取 `.env`、直写数据库并保留固定密码账号。必须整改。

### 11.1 默认安全规则

1. 默认只允许测试数据库；
2. 数据库名必须包含测试标识；
3. 连接其他数据库时立即失败；
4. 如确需开发库，必须显式参数确认，并打印目标库的脱敏标识；
5. 永远拒绝明显生产环境；
6. 默认使用随机密码；
7. 默认不打印可长期登录凭证；
8. 默认在完成后清理验收数据；
9. 只有显式 `--keep-data` 才保留；
10. 清理只删除本次 run ID 创建的数据；
11. 即使验收中途失败，也通过 finally 尝试清理；
12. 不得执行宽泛删除。

### 11.2 验收脚本不能替代自动化测试

人工脚本用于 UI/运行态补充验证，不能替代 pytest。核心安全边界必须有自动化测试。

---

## 12. 前端要求

本轮前端只做与阻断项直接相关的同步，不扩大 UI 重构。

必须确保：

1. 不显示错误的 `clarified` 文案；
2. employer closed 与 candidate answered 明确区分；
3. 前端不能通过隐藏按钮代替权限；
4. suggestion 未满足服务端证据条件时不可采纳；
5. 即使前端按钮错误开启，后端仍拒绝；
6. API 错误显示稳定用户提示；
7. loading、empty、error 状态不混淆；
8. 状态常量与后端契约一致；
9. 不新增第三套状态判断；
10. 不以 localStorage 中的 role/user ID 作为资源授权依据。

现有全局 lint 债务可以暂不全部修完，但：

- 本轮新增/修改文件不得新增 lint error；
- 必须报告修改前后的 error/warning 数；
- 不允许关闭 ESLint 规则；
- 不允许用大范围 eslint-disable 掩盖问题；
- production build 必须通过。

---

## 13. 数据库迁移要求

如果新增字段或表：

1. 使用正式、幂等迁移；
2. 不只修改 SQLAlchemy model；
3. 不只依赖启动时 `create_all`；
4. 写明 PostgreSQL 和测试 SQLite 的行为；
5. 迁移前检查现有字段；
6. 提供旧数据兼容策略；
7. 提供回滚说明；
8. 不删除或重命名数据前先获得确认；
9. 外键、唯一约束和索引与业务规则一致；
10. 测试迁移重复执行；
11. 测试旧 schema 升级；
12. 报告是否需要停机。

对于申请版本，至少考虑：

- application_id 索引；
- version number 唯一性；
- AuditRecord 到 version 的引用；
- 并发创建版本；
- JSON 大小；
- PII 保存范围；
- 删除账户时的级联策略。

---

## 14. 推荐实施顺序

严格按以下顺序执行，不并行混做：

### Step 1：建立失败测试

先新增能够复现以下问题的测试：

1. 制造申请后审计绕过；
2. 无 suggestion 任意写回；
3. 客户端伪造 evidence completed；
4. employer close 被标记 clarified；
5. rejected → accepted；
6. 换简历覆盖初始快照；
7. 邀请路径替换或制造授权；
8. 人工验收脚本可误连非测试库。

先运行并记录它们确实失败。不得直接写实现后再补只能通过的测试。

### Step 2：修授权绕过

先关闭招聘方自行制造授权的路径，再修改审计 helper。

### Step 3：修忠实写回

建立服务端 evidence 引用和 suggestion 强制校验。

### Step 4：修状态语义和迁移表

先确定状态语义，再统一 domain service，最后同步前端。

### Step 5：修快照版本

确定存储模型、迁移和历史审计引用。

### Step 6：补齐测试与验收脚本

补权限矩阵、邀请、SSE、旧数据和事务失败测试。

### Step 7：完整验证

运行后端、前端、diff 和人工验收。

### Step 8：更新文档

只有全部验收完成后，才更新状态文档。未完成项必须明确保留。

---

## 15. 必须执行的验证命令

根据当前仓库环境使用明确虚拟环境：

```bash
cd backend
.venv/bin/python -m pytest -q
```

还需要执行定向测试，例如：

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_pr1_audit_auth.py
.venv/bin/python -m pytest -q tests/test_pr2_faithful_writeback.py
.venv/bin/python -m pytest -q tests/test_pr3_state_machine.py
```

如果新增独立收口测试文件，也要单独运行。

前端：

```bash
cd frontend
npm run build
npm run lint
```

工作区检查：

```bash
git diff --check
git status --short
git diff --stat
git diff --cached --stat
```

如果项目提供迁移测试、类型检查或前端测试，也必须运行。

报告每条命令的：

- 工作目录；
- 完整命令；
- 退出码；
- passed/failed/xfail 数；
- lint error/warning 数；
- build 警告；
- 是否使用真实外部模型/API；
- 是否写入任何非测试数据库。

不得只写“测试通过”。

---

## 16. 最终验收门禁

以下任一项不满足，本轮状态必须为“未完成”：

### 安全门禁

- [ ] 招聘方不能为任意 resume 制造审计授权
- [ ] MatchResult 不构成敏感简历授权
- [ ] 无 candidate consent/application 的人才池澄清被拒绝
- [ ] 无 candidate consent/application 的邀请被拒绝
- [ ] 跨租户反馈被拒绝
- [ ] finding/claim ID 归属被严格校验

### 忠实写回门禁

- [ ] apply 必须使用服务端 suggestion
- [ ] 客户端 evidence_completed 不被信任
- [ ] requires_evidence 有真实服务端引用
- [ ] 无证据数字/角色/结果无法写回
- [ ] 失败后没有部分更新
- [ ] 重放不会重复追加

### 状态机门禁

- [ ] `clarified` 只来自候选人完成回复
- [ ] employer close 不产生 `clarified`
- [ ] 状态迁移表是唯一真相源
- [ ] 终态不能被通用 PATCH 改写
- [ ] 业务记录与状态在同一事务
- [ ] 非法迁移不写 history

### 快照门禁

- [ ] 初始投递快照不可覆盖
- [ ] 更换简历创建新版本
- [ ] 历史 AuditRecord 指向不可变版本
- [ ] legacy missing 不冒充历史快照
- [ ] 邀请/澄清不覆盖初始版本

### 工程门禁

- [ ] 完整后端测试通过
- [ ] 无新的 xfail/skip
- [ ] 前端 build 通过
- [ ] 本轮没有新增 lint error
- [ ] diff check 通过
- [ ] 没有覆盖用户已有改动
- [ ] 没有写入非测试数据库
- [ ] 没有开始 PR4 或后续任务

---

## 17. Cursor 最终报告固定格式

完成后必须按以下格式报告：

```text
# PR0–PR3 收口执行报告

## 1. 总体状态
- 完成 / 部分完成 / 阻塞
- 未完成时列出阻断原因

## 2. 开始前工作区状态
- branch
- staged 文件
- unstaged 文件
- untracked 文件
- 如何保护用户改动

## 3. 问题与根因
- 阻断项一
- 阻断项二
- 阻断项三
- 阻断项四
- 阻断项五

## 4. 修改文件
- 文件
- 修改原因
- 行为变化
- 是否包含任务开始前的用户改动

## 5. 授权变化
- 合法访问条件
- 被拒绝路径
- 防枚举行为
- 旧数据行为

## 6. 忠实写回变化
- suggestion 真相源
- evidence 真相源
- apply 校验
- 审计记录

## 7. 状态机变化
- 状态迁移表
- derived status 条件
- terminal status 规则
- employer close 语义

## 8. 快照和版本
- 初始快照
- 当前版本
- 旧版本
- AuditRecord 引用
- legacy 兼容

## 9. 数据库迁移
- migration 内容
- 旧数据数量/影响
- 幂等性
- 回滚方式
- 是否需要停机

## 10. 新增和修改的测试
- 测试文件
- 测试名称
- 对应风险
- 修复前是否失败
- 修复后结果

## 11. 实际执行命令
- 命令
- 工作目录
- 退出码
- 完整结果数量

## 12. 前端验证
- build
- lint 修改前
- lint 修改后
- 新增错误

## 13. 人工验收
- 步骤
- 结果
- 使用的数据库
- 数据是否清理

## 14. 未解决风险
- 不得省略

## 15. 工作区保护确认
- 未 reset
- 未 checkout/restore
- 未 clean
- 未覆盖用户改动
- 未修改无关 staged 内容
- 未开始 PR4
```

---

## 18. 可直接复制给 Cursor 的启动命令

```text
完整阅读 CURSOR_PR0_PR3_CLOSURE_SPEC.md、PR3_IMPLEMENTATION_SPEC.md、
CURSOR_DEFINITION_OF_DONE.md、CURSOR_EXECUTION_BACKLOG.md、
CURSOR_REMEDIATION_PLAN.md、AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md 和当前 git 状态。

本轮只执行 PR0–PR3 收口，不执行 PR4 或任何后续功能。

严格遵守 CURSOR_PR0_PR3_CLOSURE_SPEC.md 的工作区保护、禁止捷径、
实施顺序、测试矩阵和迁移要求；PR3 具体实现遵守 PR3_IMPLEMENTATION_SPEC.md，
所有完成判定遵守 CURSOR_DEFINITION_OF_DONE.md。

开始修改前，先报告：
1. 当前 staged/unstaged/untracked 状态；
2. 五个阻断项的根因；
3. 涉及文件；
4. 数据库与旧数据影响；
5. 先失败后修复的测试计划；
6. 如何避免覆盖现有用户改动。

必须先新增能复现问题的失败测试，再做实现。不得削弱断言、不得 xfail、
不得只修前端、不得信任客户端 evidence_completed、不得将招聘方自行创建的
JobApplication 当成候选人授权、不得把 employer close 标记为 clarified、
不得覆盖初始投递快照。

所有阻断项和门禁完成后，执行完整后端测试、定向测试、前端 build/lint、
git diff 检查，并按文档第 17 节输出完整报告。任何一项未完成都必须明确报告，
不要提前更新“已完成”状态，也不要开始 PR4。
```

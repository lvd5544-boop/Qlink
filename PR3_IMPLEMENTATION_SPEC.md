# PR3 可执行规格：申请状态机、Claim 澄清与简历版本不可变

> 版本：2026-07-24  
> 权威范围：只约束 PR3。与其他文档冲突时，本文件对 PR3 的行为定义优先。  
> 当前状态：仓库已有部分 PR3 实现；Cursor 必须先审计、补缺和验证，禁止重新平行实现一套。

## 0. 本批次完成后必须实现的用户结果

### 候选人看到的结果

1. 不能通过任何通用状态接口把自己的申请标记成“已澄清”“面试邀请”“已录用”或“已拒绝”。
2. 一条 Claim 回复只更新对应线程；还有开放 Claim 时仍显示“待澄清”。
3. 只有所有 Claim 都得到候选人有效回复时，才显示“候选人已说明，待招聘方复核”。
4. 招聘方人工关闭未回复 Claim 时，显示“招聘方已关闭，候选人未说明”，不得显示“已澄清”。
5. 重复投递、招聘方澄清和面试邀请不能静默更换申请绑定的简历。
6. 主动更换简历必须显式确认；招聘方已经查看、审计、澄清或邀请后，不允许覆盖其已看到的版本。
7. 所有历史记录都能说明当时使用了哪一份简历。

### 招聘方看到的结果

1. 通用状态操作只能执行明确允许的人工招聘动作。
2. “待澄清”“候选人已说明”“面试邀请”只能由对应业务动作产生。
3. 不能用人才池中的另一份简历替换已有申请的简历。
4. 人工关闭澄清必须填写原因并保留关闭人、时间和未回复语义。
5. 发送邀请必须创建邀请记录、申请时间线消息和状态历史；任一数据库步骤失败时不能留下半成品。

## 1. PR3 范围

### 必须完成

- 建立单一申请状态迁移服务；
- 阻断通用状态 PATCH 对派生状态的写入；
- 明确招聘终态不可回退；
- 修正 Claim 全部回答和人工关闭的不同语义；
- 自动路径禁止更换 `resume_id`；
- 建立不可变投递快照、当前活动快照和换简历历史；
- 审计、澄清、邀请都绑定明确简历版本；
- 前后端状态枚举、标签、筛选和按钮一致；
- 覆盖权限、迁移、版本、并发/幂等和失败回滚测试。

### 本批次不做

- 不实现完整 Claim Passport；
- 不训练模型；
- 不重写可信度评分；
- 不处理全仓权限审计（属于 PR4）；
- 不实现原子 LLM 配额或 WebSocket ticket（属于 PR5）；
- 不做全仓模块重构和术语收敛（属于 PR5.5）；
- 不把面试回答自动升级为“已验证证据”。

## 2. 先审计当前部分实现

当前已存在：

- `backend/app/application_state.py`；
- `backend/tests/test_pr3_state_machine.py`；
- `capture_resume_snapshot`、`ensure_resume_unchanged` 和显式换简历接口；
- 业务动作调用 `set_application_status`；
- PR3 与原 Findings 测试当前可以通过。

“测试通过”不等于本规格完成。Cursor 必须逐项核验以下已知缺口：

1. `application_status.EMPLOYER_SETTABLE_STATUSES` 仍包含派生状态，与领域服务定义冲突；
2. `set_application_status` 只检查枚举，不检查完整迁移图和终态回退；
3. 招聘方人工关闭 Claim 目前被重算成 `clarified`，语义错误；
4. 当前 PR3 测试把人工关闭断言成 `clarified`，需要改成更严格的正确语义；
5. `capture_resume_snapshot` 未明确深拷贝语义；
6. 显式换简历会覆盖当前 `resume_snapshot`，原始投递快照与活动版本没有清晰分离；
7. 审计记录只通过 `resume_id` 难以表达“审计发生时的具体版本”；
8. Claim 线程与状态存于 JSON，两个并发回复可能发生丢失更新；
9. `application.status` 同时承载招聘阶段和澄清阶段，是待 PR5.5 收敛的兼容设计；PR3 不得再增加第三套状态真相源；
10. `_save_clarification_answer_to_resume` 仍会把澄清回答写进工作简历；PR3 只需保证投递快照不受污染，并登记为 PR8 前必须拆分的后续问题。

## 3. 状态词义

### 3.1 状态枚举

PR3 允许：

- `submitted`：已投递，招聘方尚未查看；
- `viewed`：招聘方已查看；
- `needs_clarification`：至少存在一条开放 Claim；
- `clarified`：所有相关 Claim 都由候选人回答，等待或完成招聘方复核；
- `clarification_closed`：招聘方关闭了未回答 Claim；不表示候选人已经说明；
- `interview_invited`：成功创建面试邀请；
- `rejected`：招聘流程终止；
- `accepted`：招聘流程完成。

前后端标签必须分别为：

| 状态 | 候选人文案 | 招聘方文案 |
|---|---|---|
| submitted | 已申请 | 新申请 |
| viewed | 招聘方已查看 | 已查看 |
| needs_clarification | 待补充说明 | 等待候选人说明 |
| clarified | 已提交说明 | 候选人已说明，待复核 |
| clarification_closed | 招聘方已关闭澄清 | 已关闭，候选人未说明 |
| interview_invited | 已收到面试邀请 | 已发送面试邀请 |
| rejected | 未进入后续流程 | 已拒绝 |
| accepted | 已录用 | 已录用 |

禁止使用“已验证真实”“无造假”“确认属实”。

### 3.2 业务动作专属状态

以下状态不能由 `PATCH /applications/{id}/status` 设置：

- `needs_clarification`；
- `clarified`；
- `clarification_closed`；
- `interview_invited`。

候选人不能通过通用状态接口设置任何状态。

### 3.3 终态

`accepted` 和 `rejected` 是终态：

- 通用 PATCH 不得从终态回到任何状态；
- 澄清、换简历和邀请动作默认返回 409；
- 只读消息、审计历史和导出仍可访问；
- 如果未来需要重新开启，必须另建专用动作并留痕，不属于 PR3。

## 4. 唯一迁移图

`application_state.py` 必须包含一张可测试的迁移表，而不是在路由里散落条件。

| 当前状态 | 业务动作 | 目标状态 | 结果 |
|---|---|---|---|
| submitted | 招聘方查看 | viewed | 允许 |
| submitted/viewed/clarified/clarification_closed | 创建首条开放 Claim | needs_clarification | 允许 |
| needs_clarification | 回答一条但仍有 open | needs_clarification | 保持 |
| needs_clarification | 回答最后一条 open | clarified | 允许 |
| needs_clarification | 招聘方关闭全部 open | clarification_closed | 允许，必须记录原因 |
| submitted/viewed/clarified/clarification_closed | 成功创建邀请 | interview_invited | 允许 |
| needs_clarification | 创建邀请 | — | 409；先回答或显式关闭澄清 |
| submitted/viewed/clarified/clarification_closed/interview_invited | 拒绝 | rejected | 允许 |
| submitted/viewed/clarified/clarification_closed/interview_invited | 录用 | accepted | 允许 |
| interview_invited | 再次查看/澄清/邀请 | — | 查看幂等；其他动作按规则拒绝 |
| accepted/rejected | 任意写动作 | — | 409 |

同状态写入只能在明确幂等的业务动作中返回当前结果，不得追加虚假状态历史。

## 5. 后端实现路径

### 5.1 `backend/app/application_status.py`

目标：

- 只保留枚举和显示标签；
- 删除或废弃与 `application_state.py` 冲突的可写状态集合；
- 加入 `clarification_closed`；
- 不在这里实现第二套迁移逻辑。

验收：

- 全仓只有一个“谁可以从什么状态迁移到什么状态”的权威定义。

### 5.2 `backend/app/application_state.py`

目标：

1. 定义：
   - `APPLICATION_TRANSITIONS`；
   - `BUSINESS_ACTION_ONLY_STATUSES`；
   - `TERMINAL_STATUSES`；
   - `validate_transition(current, target, action, actor_role)`；
2. 所有状态变化通过一个受控入口；
3. 状态历史记录：
   - from/to；
   - action/source；
   - actor_id/role；
   - reason；
   - timestamp；
   - request/idempotency key（如有）；
4. 相同状态的幂等调用不追加历史；
5. 终态回退统一返回 `StatusTransitionError(code=409)`。

禁止：

- 仅验证 `new_status in APPLICATION_STATUSES` 就赋值；
- 让调用方通过任意 `source` 绕过迁移图；
- 在路由中直接写 `application.status = ...`。

### 5.3 `backend/app/claim_threads.py`

目标：

- `open`、`answered`、`reviewed`、`closed` 状态语义稳定；
- `closed` 与 `answered/reviewed` 分开计算；
- `recompute_clarification_status`：
  - 有 open → `needs_clarification`；
  - 无 open 且至少一条由候选人 answered/reviewed、没有人工未答关闭 → `clarified`；
  - 无 open 且存在人工关闭未回答 → `clarification_closed`；
- 关闭记录必须含 `closed_by`、`closed_at`、`close_reason`；
- 重复关闭返回 400/409，不伪造第二条历史；
- 同一 Claim 的新一轮澄清不得覆盖旧线程历史，应使用 revision/round 或新 thread key。

并发要求：

- 回复和关闭前锁定申请行，或使用等价的乐观版本检查；
- 两个并发回复不能丢失其中一条；
- 回复已经关闭/回答的 Claim 返回冲突；
- 最后一条 Claim 的状态重算与消息保存处于同一事务。

### 5.4 `backend/app/application_routes.py`

逐入口要求：

#### `POST /applications`

- 候选人只能投递自己的简历；
- 首次创建记录不可变 `initial_submission_snapshot` 和首个 `resume_versions` 项；
- 重复投递相同 resume：幂等返回原申请；
- 重复投递不同 resume：不改变原申请，返回 `resume_change_required_explicit=true`。

#### `PATCH /applications/{id}/status`

- 只做鉴权、解析和调用领域服务；
- employer 只能执行迁移图允许的 viewed/rejected/accepted；
- candidate 全部拒绝；
- 派生状态全部拒绝；
- 非本人资源拒绝；
- 终态回退返回 409。

#### `POST /applications/{id}/clarification-requests`

- 只有岗位 owner 可调用；
- 终态和 `interview_invited` 拒绝；
- 创建消息、Claim thread、状态历史在一个事务内；
- 失败时三者均不落库。

#### `POST /applications/{id}/clarification-response`

- 只有申请 candidate 可调用；
- 必须绑定正确 open Claim；
- 保存 response、更新 thread、重算状态在同一事务；
- 多 Claim 只回答一个时仍为 `needs_clarification`；
- 最后一条有效回复后才为 `clarified`。

#### `POST /applications/{id}/clarification/close`

- 只有岗位 owner；
- 必须存在 open Claim；
- reason 去空格后不能为空，长度设上限；
- 关闭后状态为 `clarification_closed`；
- 返回 `closed_claim_count` 和线程留痕；
- UI/响应不得写“候选人已澄清”。

#### `PATCH /applications/{id}/resume`

允许条件必须全部满足：

- 当前用户是申请 candidate；
- `confirm=true`；
- 新简历属于该 candidate；
- 新旧 resume 不同；
- 申请不是终态；
- 招聘方尚未查看；
- 没有审计记录、澄清消息、面试邀请或其他 employer activity。

否则返回 400/403/404/409 中与原因匹配的状态，不改变任何数据。

### 5.5 简历快照

在 `pipeline_meta` 的 PR3 兼容实现中明确三个概念：

```json
{
  "initial_submission_snapshot": {
    "resume_id": "...",
    "parsed_json": {},
    "captured_at": "...",
    "content_hash": "sha256:..."
  },
  "current_resume_version_id": "v1",
  "resume_versions": [
    {
      "version_id": "v1",
      "resume_id": "...",
      "snapshot_json": {},
      "content_hash": "sha256:...",
      "source": "candidate_applied",
      "actor_id": "...",
      "created_at": "..."
    }
  ]
}
```

规则：

- `initial_submission_snapshot` 创建后永不覆盖；
- 首个 `resume_versions` 项与初始快照内容一致；
- 显式更换只能追加 `resume_versions`，并更新 `current_resume_version_id`，不能修改旧项；
- 对 JSON 做深拷贝，不能与 `Resume.parsed_json` 共享可变引用；
- 换简历历史保存前后 ID、前后 hash、actor、reason、time；
- 旧字段 `resume_snapshot` 需要一次性兼容读取策略，不能静默丢失；
- PR7 引入正式 `ResumeVersion`/Alembic 后再迁出 JSON。

审计规则：

- 新审计明确使用 `current_resume_version_id` 指向的不可变版本；
- 审计记录保存 snapshot resume ID/hash/captured_at；
- 历史审计重新查看时使用当次 audit snapshot，不使用当前 Resume；
- 投递原始内容始终可以由 `initial_submission_snapshot` 复现。

### 5.6 `backend/app/invitation_routes.py`

- `application_id` 存在时必须验证 job、candidate、resume、employer 全部一致；
- 仅有相同 job 不足以复用申请；
- 已有申请时请求 resume 必须等于当前版本绑定的 resume；
- 有 open Claim 时返回 409；
- 创建 application（必要时）、invitation、message、status history 必须同事务；
- 数据库提交成功后再发布 event；
- 邮件失败不删除已创建邀请，但必须记录 notification failure，不能静默当作邮件成功；
- 重复 idempotency key 或已有 pending invitation 返回同一资源或明确冲突，不重复创建。

## 6. 前端实现路径

涉及：

- `frontend/src/constants/applicationStatus.js`；
- `frontend/src/pages/Candidate/AppliedJobs.jsx`；
- `frontend/src/pages/Employer/Applications.jsx`；
- `frontend/src/pages/Employer/CandidateList.jsx`；
- 邀请和申请 API 封装。

要求：

1. 加入 `clarification_closed` 文案和筛选；
2. 招聘方人工关闭弹窗必须填写原因；
3. `clarified` 页面固定显示“候选人已说明，不代表事实已验证”；
4. `clarification_closed` 显示“招聘方关闭，候选人未说明”；
5. 仍有 open Claim 时隐藏/禁用邀请按钮，解释下一步；
6. 邀请只调用 invitation action，不再调用通用状态 PATCH；
7. 重复投递不同简历时显示确认流程，不让用户误以为已自动替换；
8. 后端 409 显示具体冲突，不吞掉错误；
9. 不复制后端迁移图；前端仅用于按钮呈现，后端仍是权威；
10. 本批次触及文件不得新增 ESLint error/warning。

## 7. 必须新增或修正的测试

### 7.1 领域单元测试

文件建议：`backend/tests/test_application_state_unit.py`

- 每条允许迁移；
- 每条禁止迁移；
- accepted/rejected 无出边；
- 相同状态幂等不增加 history；
- derived status 不能通过 generic patch；
- history 字段完整；
- 快照深拷贝；
- initial submission snapshot 不被换简历覆盖；
- legacy `resume_snapshot` 兼容读取。

### 7.2 API 集成测试

文件：扩充 `backend/tests/test_pr3_state_machine.py`

- candidate 不能 PATCH 任何状态；
- employer 不能 PATCH 四个业务动作专属状态；
- employer 只能修改本人岗位申请；
- accepted/rejected 不能回退；
- 无 Claim 不能进入 needs；
- 回复一个 Claim 后仍 needs；
- 回复最后 Claim 后 clarified；
- 人工关闭后 `clarification_closed`，且原因/人/时间完整；
- 人工关闭不产生 candidate response；
- open Claim 时邀请返回 409；
- 邀请成功才进入 interview_invited；
- invitation 数据库失败时不改变 application status；
- 重复投递不同简历不替换；
- 人才池另一简历发起澄清返回 409；
- 人才池另一简历发邀请返回 409；
- 显式换简历未确认失败；
- 非本人简历失败；
- viewed/audited/clarified/invited/terminal 后换简历均失败；
- 允许换简历时 initial submission snapshot 不变、追加新版本并更新 current version；
- 历史审计使用当次 snapshot。

### 7.3 并发和幂等测试

- 两个 Claim 同时回复均被保留；
- 回复与人工关闭竞争时最多一个成功，状态可解释；
- 两次相同邀请不创建两个 pending invitation；
- 两次重复投递返回同一 application。

SQLite 无法证明 PostgreSQL 锁语义时：

- 保留快速 SQLite 单测；
- 增加标记为 integration 的 PostgreSQL 测试；
- 文档记录 CI 如何启动 PostgreSQL；
- 不得以“SQLite 通过”宣称并发已验证。

### 7.4 前端验证

- 状态映射单元测试；
- 候选人多 Claim 回复交互；
- 人工关闭文案；
- open Claim 时邀请按钮；
- 换简历确认和 409；
- production build；
- PR3 涉及文件的 scoped ESLint；
- 全局 lint 基线不得恶化。

## 8. 数据迁移与兼容

PR3 开始前 Cursor 必须输出：

1. 当前数据库中各 application status 数量；
2. 是否存在 Claim 全部 closed 但 application 为 clarified；
3. 是否存在 resume ID 与 snapshot ID 不一致；
4. 是否存在无 snapshot 的历史申请；
5. 是否存在终态后仍发生状态回退的 history。

禁止自动修改真实数据。先生成只读审计报告。

兼容策略：

- 旧 `resume_snapshot` 首次迁移为 `initial_submission_snapshot + resume_versions[0] + current_resume_version_id`；
- 旧的 employer-closed + clarified 数据映射为 `clarification_closed`；
- 无法判断来源的数据标记 `migration_uncertain=true`，进入人工列表；
- 所有迁移必须可重复执行、可回滚并记录数量；
- 若项目尚未使用 Alembic，PR3 不得继续增加启动时任意 DDL；正式迁移在 PR7 完成。

## 9. 事务与失败语义

以下内容必须在同一个数据库事务：

- 澄清请求消息 + Claim thread + application status/history；
- 澄清回复消息 + thread answer + status/history；
- 人工关闭 threads + status/history；
- 邀请记录 + application 绑定 + timeline message + status/history；
- 显式换简历 + 新 version + current version 指针 + change history。

失败时：

- 不提交部分记录；
- 不提前发布 SSE；
- 返回稳定错误码；
- 日志包含 request ID、application ID 和 action，不记录简历正文/证据正文；
- 外部邮件、模型或事件服务失败不能制造错误数据库状态。

## 10. PR3 Definition of Done

只有以下全部满足才可写“PR3 完成”：

- [ ] baseline Findings 文件无 XFAIL；
- [ ] PR3 领域与 API 测试全部通过；
- [ ] 完整后端测试无 XFAIL/XPASS；
- [ ] PostgreSQL 并发测试通过，或明确标为阻断项而非假装完成；
- [ ] 前端 production build 通过；
- [ ] PR3 触及文件 scoped ESLint 无新增问题；
- [ ] 全局 lint 数量未恶化并报告数字；
- [ ] `rg` 证明没有路由直接写 `JobApplication.status`；
- [ ] `rg` 证明自动路径没有直接改已有 application `resume_id`；
- [ ] 人工关闭不再显示 clarified；
- [ ] initial submission snapshot 可复现且不会被覆盖；
- [ ] 前后端状态标签一致；
- [ ] 数据审计与迁移报告完成；
- [ ] 手工完成候选人和招聘方两条冒烟流程；
- [ ] 没有覆盖任务开始前已有用户改动；
- [ ] 输出遗留问题，并明确属于 PR4、PR5、PR5.5、PR7 或 PR8。

任一项未满足，状态只能写“PR3 部分完成”。

## 11. Cursor 执行提示

```text
完整阅读 CURSOR_PR0_PR3_CLOSURE_SPEC.md、PR3_IMPLEMENTATION_SPEC.md、CURSOR_DEFINITION_OF_DONE.md、CURSOR_EXECUTION_BACKLOG.md、CURSOR_REMEDIATION_PLAN.md 和当前 git status。
当前仓库已有部分 PR3 实现，不要重新平行实现。先逐项输出“已满足/部分满足/未满足”的差距矩阵，并列出证据文件和行号。
先新增或修正会失败的测试，再修改业务代码。特别修正：人工关闭不得映射为 clarified、终态不可回退、initial submission snapshot 不可覆盖、并发更新不得丢失。
本轮只做 PR3，不做 PR4、PR5、PR5.5、Claim Passport、模型训练或全仓重构。
每完成一个子目标立即运行最小相关测试；最后运行完整后端、前端 build、scoped lint 和全局 lint 基线。
除非 PR3 Definition of Done 全部满足，否则不得报告“PR3 已完成”。
保留全部已有暂存、未暂存和未跟踪改动；禁止 reset、checkout、覆盖、批量格式化或关闭规则。
```

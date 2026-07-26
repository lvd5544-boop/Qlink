# PR5.1 实施与验证报告

> 状态：**最终完成**（2026-07-25 门禁关闭）  
> 日期：2026-07-25  
> 关闭证据：`PR6_FINAL_GATE_CLOSURE.md`、`PR6_E2E_EVIDENCE/`

## 1. 产品规则

- Candidate Pro：¥20/月；
- Candidate Free 与 Pro：Resume Coach 50/月、忠实重写 50/月；
- 企业：¥300/席位/月，共享可信度审计 300 credits/月；
- 加购包：¥100/100 credits；
- AI 面试免费：50 sessions/日、50 turns/session；
- 失败或未调用模型时释放预占，不扣用户 AI credits；
- 供应商 token 与实际成本只对管理员可见；
- 持久化币种 CNY，展示 RMB，周期按 Asia/Shanghai 重置。

## 2. 实现

### 套餐与计费主体

- `Organization` / `OrganizationMembership`；
- 候选人与企业 `Plan`、`PlanEntitlement`、subscription；
- 企业共享审计额度与 credit-pack 产品；
- 注册事务内为候选人创建 Free subscription，为招聘方创建试点企业、owner 席位和
  trial subscription；
- `/billing/me`、`/billing/organization` 为用户权威权益接口。

### 三账分离

1. 套餐权益账：用户或企业账户的功能额度；
2. reservation/usage 账：原子预占、成功结算、失败释放；
3. `ProviderCostEvent`：模型、prompt 版本、token、缓存 token、价格版本与 CNY 成本。

候选人及招聘方接口不返回 token/供应商成本，管理员通过
`/admin/billing/provider-costs` 按 provider、model、feature、status 和时间区间查询。

### 失败、幂等与免费面试

- 同一 payload 在成功前复用 `Idempotency-Key`；
- `released` 可使用同 key 生成下一 attempt，成功只落一条 usage；
- 未调用模型的规则路径不预占或不结算 AI credits；
- 模型调用后业务失败仍记录管理员成本事件，但用户 reservation 为 `released`；
- 免费面试使用持久化 session、公平使用计数、单用户 active session 约束；
- 每次真实面试/抽取/追问模型调用均记录实际 usage，免费但不隐藏平台成本。
- 每次供应商调用前执行平台级日容量保护，默认
  `INTERVIEW_GLOBAL_PROVIDER_CALLS_PER_DAY=5000`；生产 Redis 不可用时保护性拒绝，
  不把容量拒绝记成用户失败调用或扣用户 credits。

### 面试数据用途与撤回

- 面试开始前提供“简历辅助、个人推荐、招聘方分享、模型改进”四个独立开关；
- 开始前用途意向写入 `requested_uses`，不会冒充已授权的 `allowed_uses`；
- 面试结束只生成候选人所有的 `InterviewResult` 待确认草稿，不再自动改写最新简历，
  也不再自动生成招聘方可见纪要；
- 候选人结束后再次逐项确认；只有明确授权才写简历或分享给绑定申请的招聘方；
- 待确认草稿支持刷新恢复且只能本人读取；
- 撤回会清空 transcript、结构化结果和来源引用，并删除本结果生成的简历数据与招聘方
  消息；对候选人之后手工修改过的字段不做破坏性覆盖；
- “岗位推荐”表示是否直接把面试草稿作为额外推荐信号；确认写入正式简历后的内容仍按
  普通简历规则使用；
- 模型改进默认关闭；当前没有训练管线会读取面试草稿。

### 忠实度

- 中文插入新专名/事实会命中 `unsupported_inserted_span`；
- proof 使用独立 `FIDELITY_PROOF_SECRET_KEY`；
- 生产缺少独立高强度 proof key 时拒绝启动。

## 3. 数据库与回滚

正式 SQL 位于 `backend/scripts/migrations/`：

- billing core；
- metering account/attempt；
- provider cost；
- pricing/interview；
- legacy estimated cost removal；
- 每个 upgrade 均有对应、以审计数据保留为优先的 down 策略。

PR6 migration 进程建立版本账本和 checksum；Web/Worker/Scheduler 不执行 DDL。
生产回滚以“镜像回退 + 迁移前数据库/上传备份恢复”为权威方式，避免删除成本和订阅
审计链。

## 4. 验证

- SQLite PR5.1/PR5.5 定向回归：通过（PG-only 用例按标记 skip）；
- 完整 SQLite：176 selected，全部通过，6 个 PG-only skip；
- 完整 PostgreSQL：176 selected，全部通过；
- 面试目的同意定向测试：本人可见、未授权零写回、独立授权、显式分享、撤回删除和
  平台容量保护全部通过；
- 前端幂等、WS、错误契约与面试结果控制消息：13/13 通过；
- global lint：通过；
- production build：通过；
- PostgreSQL schema/并发和 migration up/down/up 测试通过；
- 隔离 PostgreSQL `jobplatform_migrate_test` 真实执行 `scripts/migrate.py` 两次：
  首次 applied ×6，第二次 skip ×6（见 `PR6_FINAL_GATE_CLOSURE.md`）；
- 浏览器面试用途选择、WS URL 无 token、结果确认与草稿撤销留证已补齐
  （见 `PR6_E2E_EVIDENCE/`）。

## 5. 商业边界

当前已实现套餐目录、权益、额度、订阅状态、成本账和展示，但尚未接入支付收单、自动
续费、退款到支付渠道、发票和税务。因而可以试点计量与人工开通，不能宣称已具备完整
线上收费闭环。

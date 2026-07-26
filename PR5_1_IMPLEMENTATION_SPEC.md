# PR5.1 实施规格：套餐权益、原子计量与安全收口

- 状态：Approved / Implemented（2026-07-25；最终外部门禁见 PR6 报告）
- 前置：`PR5_1_PRICING_AND_REMEDIATION_SPEC.md` 数值确认
- 原则：测试先行、正式 migration、最小可回滚、不得覆盖混合工作区

## 1. 当前实现差距

### 1.1 计量

- quota 直接硬编码在 `usage_metering.py`；
- 用量按 `user_id + feature + month` 统计；
- 没有 Candidate Free/Pro entitlement；
- 没有企业、席位和企业共享额度；
- `estimated_cost_usd` 是固定每调用估值，不是供应商实际 token；
- `llm_call` quota 和 `interview_turn` cost 没有调用方；
- `check_quota` / `record_usage` 已无调用方；
- 客户端没有稳定复用 `Idempotency-Key`；
- reservation 不保存 request fingerprint；
- `failed` 在表约束中存在，但 finalize 失败实际写 `released`。

### 1.2 忠实度

- 数字、英文 token、角色升级和片段覆盖已有规则；
- 中文公司、产品、平台、证书等实体未进入受保护事实集合；
- 当前阈值允许在长句中插入少量中文专名；
- 没有固定、版本化的实体对抗评测集。

### 1.3 WebSocket

- JWT 已从 URL 移到首消息；
- 服务端有 auth timeout 和资源归属校验；
- 前端没有独立 authenticating/timeout/failed 状态；
- 1008 关闭统一显示“面试已结束”；
- 免费面试没有 session/轮次 fair-use 和实际 token 成本记录。

## 2. 权威模块边界

建议新增或收拢为：

```text
backend/app/billing/
  plans.py                 套餐和 entitlement 读取
  accounts.py              user/org 计费主体解析
  reservations.py          reserve/finalize/retry
  provider_costs.py        实际 token 成本
  interview_limits.py      免费面试 fair-use
  schemas.py               稳定错误和返回模型

backend/app/fidelity/
  entities.py              中英文受保护实体
  policy.py                原子事实来源覆盖
  proofs.py                proof 签发与验证

backend/app/websocket_auth.py
  仅处理首消息认证和资源授权
```

为控制 PR5.1 范围，第一步可以使用现有文件并逐步移动；不得一次性重写所有
route。PR5.5 再完成最终模块收敛。

## 3. 数据模型

### 3.1 `organizations`

招聘企业的计费与权限主体。

关键字段：

- `id`
- `name`
- `status`
- `created_at`
- `updated_at`

不得复用现有市场画像 `companies` 表；`companies` 是推荐/市场数据，不代表
登录用户所属的法律或计费组织。

### 3.2 `organization_memberships`

- `organization_id`
- `user_id`
- `role`: owner/admin/recruiter
- `status`: active/invited/disabled
- `created_at`
- 唯一约束：`organization_id + user_id`

所有 employer 必须通过 membership 占用一个席位。

### 3.3 `plans`

- `code`
- `audience`: candidate/organization
- `name`
- `currency`: CNY
- `price_minor_units`
- `billing_period`: month
- `version`
- `active`

价格以分存储，禁止浮点货币。

### 3.4 `plan_entitlements`

- `plan_code`
- `feature`
- `limit`
- `period`: day/month/session
- `meter_type`: paid_credit/fair_use/unmetered
- 唯一约束：`plan_code + feature + period`

### 3.5 `user_subscriptions`

- `user_id`
- `plan_code`
- `status`
- `period_start`
- `period_end`
- `cancel_at_period_end`
- `source`: manual/payment_provider/pilot

支付渠道不在 PR5.1；允许管理员或 seed 创建 pilot subscription。

### 3.6 `organization_subscriptions`

- `organization_id`
- `plan_code`
- `seat_quantity`
- `status`
- `period_start`
- `period_end`
- `cancel_at_period_end`

共享 credits 归 organization subscription，不归 recruiter 用户。

### 3.7 `usage_reservations` 升级

保留现表并新增：

- `billing_account_type`: user/organization
- `billing_account_id`
- `request_fingerprint`
- `attempt`
- `error_code`
- `model_called`
- `finalized_at`

状态收敛为：

- `reserved`
- `succeeded`
- `released`

唯一约束至少覆盖：

`billing_account_type + billing_account_id + feature + period_key +
idempotency_key + attempt`

同一幂等键同一时刻只能存在一个 `reserved` attempt。

### 3.8 `provider_cost_events`

- `id`
- `reservation_id`，免费面试可为空
- `user_id`
- `organization_id`，可空
- `feature`
- `provider`
- `model`
- `model_version`
- `prompt_version`
- `provider_request_id`
- `input_tokens`
- `output_tokens`
- `cache_hit_tokens`
- `cache_miss_tokens`
- `currency`
- `cost_minor_units`
- `price_version`
- `provider_status`
- `created_at`

管理员权限之外不得返回 token 和成本字段。

## 4. Migration 顺序

建议拆为两个可回滚 migration：

### Migration A：权益主体

1. 创建 organizations；
2. 创建 memberships；
3. 创建 plans / entitlements；
4. 创建 user / organization subscriptions；
5. 为现有 candidate 建立 Free subscription；
6. 为现有 employer 建立单成员 pilot organization；
7. 创建 organization subscription；
8. 输出迁移前后用户、employer、membership 数量；
9. 异常数据 fail closed，不静默丢弃 employer。

### Migration B：计量升级

1. 创建 provider_cost_events；
2. 为 usage_reservations 增加 account/fingerprint/attempt 字段；
3. 旧 user reservation 回填为 user account；
4. `failed` 历史记录映射规则必须在执行前确认；
5. 替换约束和索引；
6. 保留旧字段一个兼容批次；
7. downgrade 不删除既有 usage_events 和供应商成本审计。

## 5. API 契约

### 5.1 用户

- `GET /billing/me`
  - plan；
  - feature entitlements；
  - used/reserved/remaining；
  - period end；
  - 不返回实际 token 或供应商成本。

### 5.2 企业

- `GET /billing/organization`
  - plan；
  - seat quantity / active seats；
  - shared credits；
  - period end。

只有 organization owner/admin 可查看完整企业权益。

### 5.3 管理员

- `GET /admin/billing/provider-costs`
  - 支持 period/provider/model/feature/status 筛选；
  - 返回 token、缓存和成本；
  - 所有查询有分页和上限；
  - 普通 candidate/employer 必须 403。

### 5.4 稳定错误

- `quota_exceeded`：402；
- `fair_use_exceeded`：429；
- `idempotency_conflict`：409；
- `request_in_progress`：409；
- `idempotency_replayed`：409 或原结果引用；
- `billing_account_missing`：409；
- `subscription_inactive`：402。

错误 envelope 在 PR5.5 统一全局格式；PR5.1 新路径不得再依赖自由文本。

## 6. 模型调用包装

所有受计量模型调用必须通过一个可审计 wrapper：

```text
resolve entitlement
  → reserve
  → call provider
  → capture provider usage
  → validate output
  → persist business result
  → finalize succeeded
```

异常路径：

```text
provider called?
  ├─ no  → release，无 cost event
  └─ yes → 保存 cost event → release 用户额度
```

规则降级：

```text
no provider call
  → no reservation consumption
  → no provider cost
  → 可记录免费 product event
```

## 7. 忠实度实现要求

1. 将 source 拆为可追溯原文、用户回答和允许结构化字段；
2. 提取数字、日期、金额、比例、角色、中英文实体；
3. 每个生成实体必须在允许来源中对齐；
4. 未识别实体不得仅依赖全句 bigram coverage 放行；
5. proof payload 记录 policy/version 和 evidence references；
6. writeback 重新验证 proof 绑定的 resume/field/value；
7. 固定对抗集至少包含：
   - 阿里云/腾讯云替换；
   - 无来源证书；
   - 无来源学校/客户；
   - 英文产品名；
   - 数字、金额、时间；
   - 参与者到负责人；
   - 合法用户回答实体；
   - 合法同义改写。

## 8. WebSocket 免费面试

服务端状态：

- unauthenticated；
- authenticated；
- active；
- closing/closed。

客户端状态：

- idle；
- connecting；
- authenticating；
- authenticated；
- auth_failed；
- auth_timeout；
- disconnected。

只有 authenticated 可以发送普通消息。

fair-use 维度：

- user + local day sessions；
- session turns；
- active connections；
- global/provider cost circuit breaker。

达到限制时使用结构化控制消息后关闭，不消耗付费 credits。

## 9. 测试先行清单

### 9.1 必须先红

1. Free/Pro entitlement 不同；
2. employer credits 在 organization 内共享；
3. 超席位邀请失败；
4. 规则路径不扣 credit；
5. provider 失败退 credit 但保存 cost；
6. 同 key 同 payload 不重复调用；
7. 同 key 不同 payload 返回 conflict；
8. 中文实体插入被拒绝；
9. WS auth timeout 提示重新登录；
10. 免费面试超过 session/turn limit 返回 fair-use error；
11. candidate/employer 不能读取 provider cost；
12. migration 回填数量一致。

### 9.2 分层回归

1. billing/fidelity/ws 单元测试；
2. PR5 HTTP 集成；
3. PostgreSQL 并发；
4. migration up/down/up；
5. 后端完整 SQLite；
6. 后端完整 PostgreSQL；
7. 前端 tests；
8. scoped/global lint；
9. production build；
10. 浏览器人工验收。

## 10. 文件级实施顺序

1. 失败测试与 migration contract tests；
2. ORM 与 migration；
3. billing account/plan policy；
4. reservation 升级；
5. provider usage wrapper；
6. 三个现有付费入口接入；
7. 免费面试 fair-use 与成本；
8. fidelity entity policy；
9. WS 客户端状态机；
10. billing 用户/企业/admin API；
11. 前端额度展示和结构化错误；
12. 清理无调用方旧函数；
13. 全量回归和验收报告。

## 11. PR5.5 / PR6 依赖

PR5.5 在 PR5.1 行为稳定后：

- 移动路由内业务逻辑到权威服务；
- 统一现有与新增错误 envelope；
- 完成术语、状态、兼容路径和 E2E；
- 不改变已经验收的计费语义。

PR6 在 PR5.5 后：

- migration 独立启动；
- Compose 单入口；
- 生产配置、readiness、规则降级；
- 持久化、备份、恢复；
- Docker-only 新环境验收。

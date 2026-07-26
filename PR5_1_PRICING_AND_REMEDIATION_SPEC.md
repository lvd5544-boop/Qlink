# PR5.1 收费、计量与安全收口行为契约

- 状态：Approved / Implemented
- 日期：2026-07-25
- 依据：
  - `CURSOR_DEFINITION_OF_DONE.md`
  - `AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`
  - `CURSOR_EXECUTION_BACKLOG.md` PR5 / PR5.5 / PR6
  - PR5 独立复验发现

## 1. 已确认的产品原则

1. 候选人采用“免费月度额度 + 订阅”。
2. 招聘方采用“企业席位 + 企业共享月度额度”。
3. AI 面试对用户免费，但必须有 fair-use 和平台成本保护。
4. 系统、模型或后处理失败时，自动退还用户额度。
5. 未调用模型的规则路径不扣 AI 额度。
6. 实际模型 token、缓存和供应商成本只对管理员可见。
7. 用户只看到功能额度、消耗记录、剩余额度和重置时间。
8. 用户额度账与平台供应商成本账必须分离。

## 2. 已确认并固化的参数

| 参数 | 最终值 |
|---|---:|
| Candidate Free Resume Coach | 50 次/月 |
| Candidate Free 忠实证据重写 | 50 次/月 |
| Candidate Pro Resume Coach | 50 次/月 |
| Candidate Pro 忠实证据重写 | 50 次/月 |
| Candidate Pro 月费 | ¥20/月 |
| 免费 AI 面试 session | 50 次/日 |
| 单次 AI 面试最大轮数 | 50 轮 |
| Employer 初始席位数 | 1 席位 |
| Employer 单席位月费 | ¥300/月 |
| Employer 月度审计 credits | 300 credits/月，企业共享 |
| Employer 额外 credit 包 | ¥100/100 credits |
| 计费币种 | CNY（人民币/RMB） |
| 月度重置时区 | Asia/Shanghai（中国标准时间） |

已确认价格全部以人民币展示和结算；代码、数据库和 API 使用 ISO 4217
币种代码 `CNY`，不使用非标准代码 `RMB` 作为持久化值。

## 3. 三套必须分离的账

### 3.1 用户权益账

记录用户或企业套餐允许使用多少功能 credits。

- 候选人额度归属于用户；
- 招聘方额度归属于企业，不归属于单个席位；
- 席位只控制企业成员访问资格；
- 免费面试不消耗付费 credits。

### 3.2 请求预占账

在昂贵操作前原子预占，防止并发超卖。

状态定义：

- `reserved`：已占额度，尚未完成；
- `succeeded`：成功交付用户结果，正式消耗额度；
- `released`：未交付结果，额度已退还；
- 不保留没有明确业务语义的 `failed` 状态。

失败原因、供应商是否已计费、实际 token 等进入独立字段/事件，不能用
reservation 状态同时表达用户权益与平台成本。

### 3.3 供应商成本账

每次真实模型请求都记录：

- provider；
- model ID / model version；
- prompt/template version；
- input tokens；
- output tokens；
- cache-hit tokens；
- cache-miss tokens；
- provider request ID（若有）；
- provider-reported status；
- 实际或按当时价格表计算的成本；
- 价格表版本；
- 关联 reservation/request ID。

用户退款不得删除供应商成本事件。

## 4. 核心行为契约

### 4.1 成功的付费 AI 功能

Given：

- 用户具有对应套餐权益；
- 当月剩余额度至少为 1；
- 请求携带有效且稳定的 `Idempotency-Key`。

When：

- 服务端完成模型调用、结果校验和持久化；
- 用户获得可使用的业务结果。

Then：

- reservation 从 `reserved` 变为 `succeeded`；
- 用户额度消耗 1；
- 只生成一个成功用量事件；
- 若调用了模型，记录实际 token 成本；
- 相同幂等键重放不得重复调用模型或重复扣除。

### 4.2 规则路径未调用模型

Given：

- 功能采用确定性规则或严格拼接完成；
- 未向外部模型供应商发出请求。

When：

- 规则结果成功返回。

Then：

- 不消耗 AI credits；
- 不生成模型成本事件；
- 可以生成不计费的产品行为/审计事件；
- UI 不得把它展示成一次付费 AI 调用。

### 4.3 模型或系统失败

Given：

- 已预占用户额度。

When：

- 模型超时、供应商错误、输出校验失败、后处理失败或持久化失败；
- 用户没有获得可使用的最终结果。

Then：

- reservation 变为 `released`；
- 用户额度自动退还；
- 返回稳定结构化错误码；
- 若供应商已经产生 token，用独立成本事件记录；
- 相同请求的安全重试复用原幂等键，不重复制造并发调用。

### 4.4 用户输入错误

Given：

- 请求在模型调用前即可判定为 400/422。

Then：

- 不创建 reservation，或立即 release；
- 不消耗额度；
- 不产生模型成本；
- 返回字段级稳定错误码。

### 4.5 幂等重放

- 同 key、同请求指纹、执行中：返回 `request_in_progress`；
- 同 key、同请求指纹、已成功：返回原结果或稳定 replay 响应；
- 同 key、不同请求指纹：返回 409 `idempotency_conflict`；
- 已 release 的请求是否允许同 key 重试，必须采用单一全局规则；
- 前端不得在网络重试时自动生成新 key。

建议规则：同 key 在 `released` 后允许一次新的执行 attempt，并保留 attempt
历史；同一时刻最多一个 attempt 处于 `reserved`。

### 4.6 免费 AI 面试

AI 面试不消耗候选人付费 credits，但不是无限资源：

- 每用户每日 session 上限；
- 单 session 轮次上限；
- 单用户并发连接上限；
- 认证失败、空消息和异常频率限制；
- 平台全局成本熔断；
- 达到 fair-use 限制使用 429 和稳定错误码；
- 面试实际 token 仍进入管理员成本账。

不得因为面试免费而跳过：

- WebSocket 身份认证；
- resume/application 归属校验；
- token 成本记录；
- 敏感数据和 allowed-use 控制。

## 5. 权益模型

建议引入以下概念，具体表结构在 migration 规格中确定：

- `plans`：候选人/企业套餐定义；
- `plan_entitlements`：功能额度及周期；
- `user_subscriptions`：候选人订阅；
- `organizations`：招聘企业；
- `organization_memberships`：企业席位；
- `organization_subscriptions`：企业套餐；
- `usage_reservations`：原子预占；
- `usage_events`：用户权益消耗；
- `provider_cost_events`：真实模型成本。

所有套餐参数必须来自数据库或版本化配置，不从前端决定。

支付渠道、订单、退款资金流不属于 PR5.1；PR5.1 只建立正确权益和计量边界。

## 6. PR5.1 安全收口范围

除计量外，PR5.1 必须同时完成：

1. 中文公司、产品、平台、证书等专名的来源校验；
2. 每个原子事实和受保护实体均可回溯到原文或用户回答；
3. 前端稳定复用 `Idempotency-Key`；
4. WebSocket `auth_ok` 超时、1008 和重新登录提示；
5. reservation 状态语义统一；
6. 正式 migration 与运行期 schema 行为收口；
7. 删除已证明无调用方的 `check_quota` / `record_usage`；
8. 固定对抗评测集；
9. PostgreSQL 并发、迁移和 HTTP 幂等测试；
10. 浏览器人工验收证据。

## 7. PR5.5 边界

PR5.5 不增加新商业功能，只做产品与代码收敛：

- 权限、状态机、Claim、忠实写回和计量各有单一权威服务；
- 路由只负责输入输出；
- 统一错误 envelope、状态 enum、时间和术语；
- 前端收拢 feature API/hook/util；
- 兼容路径记录调用方、移除条件和截止批次；
- 建立候选人与招聘方两条 E2E 冒烟。

## 8. PR6 前置条件

只有以下条件满足后才进入 PR6：

- PR5.1 全部门禁通过；
- PR5.5 两条 canonical journey 和 E2E 通过；
- migration 是数据库变化权威入口；
- 应用启动不再承担任意 DDL；
- 生产配置和降级状态已有稳定契约。

PR6 交付：

- 单命令 Docker Compose；
- frontend/backend/PostgreSQL/Redis/worker/scheduler；
- 单入口 `/api` 与 `/ws`；
- 健康检查、持久化、备份和恢复；
- 安全 `.env.example`；
- 无模型 Key 时明确进入规则降级模式；
- 新机器 Docker-only 验收。

## 9. PR5.1 验收门禁

1. 中文专名对抗样例不能无来源写回；
2. 同 key 并发/重试只交付一次、扣一次；
3. 规则路径不消耗 AI credits；
4. 失败自动退用户额度；
5. 失败但产生 token 时管理员成本仍可见；
6. 免费面试不扣 credits，但 fair-use 和成本记录有效；
7. PostgreSQL quota 并发不超卖；
8. migration 空库 up、重复 up、down、再次 up 通过；
9. 后端完整 SQLite/PostgreSQL 回归通过；
10. 前端 test/lint/build 通过；
11. 浏览器完成 WS、409、退款和 fidelity proof 冒烟；
12. 报告列明未完成项和回滚方法。

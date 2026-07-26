# PR5 原子配额、WebSocket 凭证与忠实度：实现与验收报告

> 2026-07-25 补充：本文件记录原 PR5 基线。计费状态、面试 fair-use、用途同意、
> 成本可见性和失败退额的最终权威结论见
> `PR5_1_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`；原文中的 `failed` 四态和
> “未传幂等键由服务端随机生成”不再代表当前实现。

- 日期：2026-07-25
- 分支：`integration/phase-4-full`
- 依据：`CURSOR_EXECUTION_BACKLOG.md` 第 9 节、`CURSOR_DEFINITION_OF_DONE.md`、`AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`
- 结论：**完成**

## 1. 范围

- in_scope:
  - 原子 quota reserve/finalize、幂等、防并发超卖、失败释放；
  - WebSocket 首消息认证、query token 默认关闭、资源归属预校验；
  - 写回忠实度的受保护事实、原子片段覆盖、角色升级与来源证明；
  - `usage_reservations` 正式 upgrade/downgrade SQL。
- out_of_scope:
  - refresh token / HttpOnly Cookie；
  - PR5.5 领域模块与统一 API envelope；
  - PR6 一键部署；
  - PR7 路由拆包、完整 E2E 与 CI。

## 2. 需求追踪矩阵

| ID | 用户结果 | 实现 | 自动化测试 | 状态 |
|---|---|---|---|---|
| PR5-R01 | LLM 前原子预占 | `usage_metering.reserve_quota` | quota reservation tests | pass |
| PR5-R02 | 并发额度不超卖 | PostgreSQL advisory transaction lock + DB unique constraint | 额度 2 / 并发 8 | pass |
| PR5-R03 | 相同幂等键不重复扣费 | `usage_reservations` unique key | reserve/finalize twice | pass |
| PR5-R04 | 失败释放额度 | `finalize_quota(... succeeded=False)` | failure then retry | pass |
| PR5-R05 | 记录 reservation 状态 | reserved/succeeded/released，允许 failed | ORM + migration + summary | pass |
| PR5-R06 | JWT 不进入 WS URL | 前端纯函数构造 URL | Node URL test | pass |
| PR5-R07 | 首消息 auth / auth_ok | `websocket_auth.authenticate_websocket` | backend fake socket + frontend envelope | pass |
| PR5-R08 | WS 资源归属 | handler 前校验 resume/application | cross-resume denial | pass |
| PR5-R09 | query token 默认关闭 | `query_token_compatibility_enabled` | dev default + production override | pass |
| PR5-R10 | 数字/比例/金额/时间/专名来源 | `assess_fidelity` protected facts | fabricated percentage / user number | pass |
| PR5-R11 | 原子事实覆盖 | segment n-gram coverage | copied prefix + fabricated suffix | pass |
| PR5-R12 | 忠实同义改写 | synonym normalization | 开发/研发、优化/改进 | pass |
| PR5-R13 | 禁止角色升级 | role strength ordering | 参与者 → 主导 | pass |
| PR5-R14 | 写回记录 evidence/fidelity | signed fidelity proof + `_fidelity_history` | tamper denial + legal apply | pass |
| PR5-R15 | migration 可回滚 | up/down SQL | up/up/down/up PostgreSQL | pass |

## 3. 数据库

新增表：`usage_reservations`。

关键字段：

- `user_id`, `feature`, `month_key`;
- `idempotency_key`;
- `reserved_units`;
- `status`: `reserved/succeeded/failed/released`;
- `estimated_cost_usd`, `meta`;
- 创建与更新时间。

约束：

- `(user_id, feature, month_key, idempotency_key)` 唯一；
- 状态 check constraint；
- quota 查询复合索引。

迁移：

- upgrade: `backend/scripts/migrations/20260725_pr5_usage_reservations_up.sql`
- downgrade: `backend/scripts/migrations/20260725_pr5_usage_reservations_down.sql`
- backfill: 不需要；历史成功用量继续来自 `usage_events`
- 回滚影响：downgrade 会删除 reservation 状态，但不删除历史 `usage_events`

## 4. 行为变化

### 4.1 配额

- `resume_coach`、`evidence_regenerate`、`credibility_audit` 在昂贵工作前预占；
- 成功 finalize 并仅创建一个兼容 `UsageEvent`；
- 模型、输入或后处理失败时 release；
- worker 异常遗留的 reservation 在 TTL 后释放；
- 显式重放相同幂等键返回 409，不重复执行或扣费。

### 4.2 WebSocket

- URL 不再包含 access token；
- open 后首条消息为 `{"type":"auth","token":"..."}`；
- 只有收到 `{"type":"auth_ok"}` 后 UI 才允许发送；
- query token 默认关闭；生产环境即使设置兼容开关也关闭；
- resume/application 在进入面试 handler 前完成归属与一致性检查。

### 4.3 忠实写回

- 数字、比例、金额、时间、规模和英文专有名词逐项来源比对；
- 每个长原子片段执行来源覆盖；
- 少量公共子串不能放行大段新增事实；
- 角色强度不能从参与/协助升级为主导/负责人；
- 同义忠实改写允许通过；
- 生成结果签发 30 分钟、绑定 resume/field/value 的服务端 proof；
- 修改文字或伪造 proof 会被拒绝；
- 合法采纳保存 evidence references、fidelity version/result 和时间。

## 5. 验证

| 命令/层级 | 结果 |
|---|---|
| PR5 SQLite 专项 | 11 passed, 2 PostgreSQL-only skipped |
| PR5 PostgreSQL 专项 | 13 passed |
| 后端完整 SQLite | 128 passed, 2 skipped |
| 后端完整 PostgreSQL | 130 passed |
| 前端 Node tests | 6 passed |
| 前端 ESLint | 0 error / 0 warning |
| 前端 production build | pass；保留既有 chunk-size warning |
| migration dry-run | PostgreSQL up/up/down/up pass |
| `git diff --check` | pass |

## 6. 人工验收

1. 浏览器开发者工具中检查面试 WebSocket URL，不含 `token`。
2. 连接后首帧为 auth envelope，服务端返回 `auth_ok` 后输入框才启用。
3. 使用他人 resume/application 建立面试连接，服务端以 1008 关闭。
4. 同一 `Idempotency-Key` 重放证据生成或审计，第二次返回 409 且用量不增加。
5. 修改忠实生成结果中的数字后保留原 proof，采纳返回 400。
6. 原样采纳服务端生成结果，简历 `_fidelity_history` 可见来源与规则版本。

## 7. 兼容与回滚

- 未提供 `Idempotency-Key` 的旧客户端由服务端生成键，仍可正常使用；客户端希望安全重试时应显式复用键。
- 旧 WS query-token 客户端默认不再工作，必须升级为首消息认证。
- migration downgrade 后应同时回滚 reserve/finalize 代码到旧计费实现。
- fidelity proof 使用当前 JWT secret；轮换 secret 后，尚未采纳的旧 proof 会失效，用户需重新生成。

## 8. 尚未完成

- 短期、单用途 WS ticket 是长期增强项；本批次按规格实现首消息认证。
- 前端 access token 仍在 localStorage，HttpOnly Cookie 迁移不在 PR5 范围。
- 当前工作区在任务开始前已有混合 staged/unstaged/untracked 用户资产，本轮未 reset、checkout、覆盖或强行创建包含用户资产的提交。

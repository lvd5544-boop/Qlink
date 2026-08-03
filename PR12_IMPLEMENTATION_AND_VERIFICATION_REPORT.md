# PR12 Implementation and Verification Report

> 文档版本：2026-07-29（Codex 阻塞项修复后）  
> 范围：结构化 AI 面试官与 Claim 澄清聊天  
> 最终判定：**完成（含权限/授权/幂等/语义修复）**

## 1. Codex 阻塞项修复

| # | 问题 | 修复 |
|---|---|---|
| 1 | 客户端可扩大授权范围 | 回答 `allowed_uses` / `share_with_employer` 只能取 session consent 的交集，不可扩张 |
| 2 | `target_gap` 可绕过 `job_id` | 服务端强制 `job_required`；无岗位不再回退到 vault 题 |
| 3 | 撤回未真正撤销用途 | revoke 清空 consent、答案授权与分享标记；pending observation → rejected；会话写回 Claim 追加 revoke 事件并可撤回 interview 来源 Claim |
| 4 | 写接口无幂等 | create/next/answer/confirm/reject/complete/revoke 全部接入 `Idempotency-Key` |
| 5 | AI 状态标记失真 | Claim chat：`ai_generated=false`、`ai_connected=false`、`clarification_connected` + `generated_by=rules` |
| 6 | `vault_builder` 无法写职业记忆 | 无 claim_id 时确认写回创建 `CareerExperience` + `ResumeClaim(origin_kind=interview)` |

## 2. 二次独立验收与修复

- 重新审计授权交集、`target_gap` 岗位约束、撤回语义、写接口幂等、AI 状态标记和 Vault 写回；此前 6 个阻断项均已有回归覆盖。
- 浏览器验收时发现结构化面试岗位列表请求了不存在的候选人 `/jobs` 接口，已改为 `/browse-jobs`。
- PR12/PR13/迁移专项：`31 passed`。
- 后端全量：`299 passed, 7 skipped, 8 deselected`。
- 前端：`23 passed`，lint 通过，生产构建通过。
- 浏览器确认「结构化面试（推荐）」入口、岗位选择与 PR13 共用候选人岗位数据源可正常加载。

## 3. 残留风险（非阻断）

1. Observation 仍以规则抽取为主；Model Gateway 渲染为后续增强。
2. EvidenceFollowupModal 旧入口仍保留，属于兼容入口。
3. 当前机器 Docker daemon 与本地 PostgreSQL 均不可用，本轮无法重复执行真实 PG upgrade → downgrade → upgrade；Alembic 静态 head 已验证为 PR13。

## 4. 最终判定

**完成** — 可作为 PR13 基线。

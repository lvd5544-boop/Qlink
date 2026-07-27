# PR8 Claim Passport 实现与验收报告

日期：2026-07-27
验收依据：`CURSOR_DEFINITION_OF_DONE.md`、`CURSOR_EXECUTION_BACKLOG.md` §13、`CURSOR_REMEDIATION_PLAN.md` §5、`AI_EVIDENCE_INTERVIEW_DATA_DESIGN.md`

## 最终判定

**部分完成（本地功能与验收已通过；远端交付门禁待关闭）**

PR8 的本地功能、PostgreSQL migration、浏览器链路和专项自动化均已复验通过，
并已随 commit `44f83d7` 推送到 `origin/integration/phase-4-full`。但 PR7 所要求的
远端 GitHub Actions 全绿记录仍不可核验，因此按统一 DoD 不能标为最终「完成」。

## 范围

- in_scope：Claim Passport 关系表、证据/改写/事件、投递不可变快照、候选人补充/撤回、招聘方只读快照、文案不得暗示事实认证
- out_of_scope：区块链/RDF、高敏感原件存储、PR9 Potential Score

## 需求追踪矩阵

| ID | 用户结果 | 实现 | 自动化测试 | 人工/其他证据 | 状态 |
|---|---|---|---|---|---|
| PR8-R01 | 正式关系表：claims/evidence/revisions/links/events | `models_db.py`；`20260726_pr8_claim_passport_*.sql`；`alembic/versions/pr8_claim_passport.py` | migration unit + PG API 回归 | 隔离 PG `upgrade → downgrade(pr7) → upgrade(head)` | **pass** |
| PR8-R02 | 证据语义与工作流语义拆分 | `evidence_state` / `workflow_state` CHECK 约束；`claim_passport.py` | `test_pr8_claim_passport.py` 覆盖 supported/answered/withdrawn | UI 标签在 `ClaimPassportPanel.jsx` | **pass** |
| PR8-R03 | claim ID 跨同步保持稳定 | `sync_resume_claims` 按 `source_key` upsert | `test_claim_uuid_survives_same_source_key_text_update` | — | **pass** |
| PR8-R04 | 解析/投递时创建 Passport | `main.py` parse 路径；`application_routes` snapshot | `test_parse_resume_creates_passport_claims_immediately`；snapshot 测试 | — | **pass** |
| PR8-R05 | evidence follow-up 写入证据 | `main`/`application_routes` → `passport_add_evidence` | `test_evidence_followup_persists_candidate_answers_as_passport_evidence` | — | **pass** |
| PR8-R06 | 忠实改写写入 revision | `record_revision`；字段级稳定 Claim | `test_faithful_suggestion_apply_records_passport_revision` | — | **pass** |
| PR8-R07 | 投递快照不可变；跨租户隔离 | `snapshot_application_claims`；雇主 GET 快照 | `test_passport_application_snapshot_is_immutable_and_cross_tenant_hidden` | — | **pass** |
| PR8-R08 | 候选人可补充/撤回；撤回脱敏但留事件 | routes DELETE evidence；`withdraw_evidence` | `test_claim_sync_evidence_withdrawal_preserves_event_but_redacts_content`；跨候选人 404 | UI 撤回按钮 | **pass** |
| PR8-R09 | 招聘方只见授权申请快照 | `GET /applications/{id}/claim-passport` | 跨雇主 404 | `ApplicationClaimPassportPanel` | **pass** |
| PR8-R10 | UI 禁止「已验证真实/认证通过」 | Passport 面板文案；申请页 disclaimer | `claimPassportCopy.test.js` | 面板 Alert：「不代表事实已认证」 | **pass** |
| PR8-R11 | `conflict_detected` 可用 | 雇主冲突记录 API + candidate state | `test_authorized_employer_can_record_conflict_without_fact_verdict` | PR9 读取为 `credibility_risk` | **pass** |
| PR8-R12 | 前置 PR7/远端交付门禁 | 本地 SSE/Redis 修复已回归 | CI 等价静态检查、后端/前端测试均通过 | `44f83d7` 已推送；私有仓库 Actions 结果尚未取得 | **blocked（外部）** |

## 本回合复验命令

| 命令 | 结果 |
|---|---|
| SQLite PR8/PR9/security targeted | **60 passed，2 skipped** |
| PostgreSQL PR8/PR9/security | **52 passed** |
| 隔离 PG migration | `upgrade → downgrade(pr7_constraints) → upgrade(head)`，head=`pr9_potential_simulation`，ledger=9 |
| Browser E2E | **1 passed**：包含 Candidate Passport UI、雇主 Claim snapshot、完整招聘链路 |
| 远端 CI / 推送 | `44f83d7` 已推送到 `origin/integration/phase-4-full`；新的私有仓库 Actions 结果待核验 |

## 人工验收（抽样）

已核对：

1. 候选人 `MyResumes` 挂载 `ClaimPassportPanel`，文案区分「有用户证据支持 / 用户已说明 / 信息不足 / 冲突」，并声明非认证。
2. 招聘方 `Applications` 挂载 `ApplicationClaimPassportPanel`，说明投递后私密补充不可见。
3. 语义上未发现 Passport UI 使用「已验证真实」「认证通过」。

隔离 PostgreSQL 升降级和浏览器全链路 E2E 已于本回合真实复跑。

## 尚未完成（阻断「完成」）

1. **PR7 / PR8 的远端 GitHub Actions 全绿**仍未取得；本环境不能在未获凭据授权的情况下核验私有仓库运行记录。

## 兼容与回滚

- 迁移：`20260726_pr8_claim_passport_down.sql` / Alembic `pr8_claim_passport`
- 回滚后需停止依赖 Passport 路由的前端面板，避免 404

## 工作区保护

- 验收过程未执行 `git reset`/`checkout --` 覆盖用户改动。
- 结论与实现报告已改写为「部分完成」，纠正此前「已完成」表述。

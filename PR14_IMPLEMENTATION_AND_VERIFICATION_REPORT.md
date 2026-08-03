# PR14 Implementation and Verification Report

> 文档版本：2026-07-30（独立验收）  
> 范围：四层画像、合法数据流水线与 AI 求职顾问  
> 最终判定：**完成**

## Outcome

PR14 is implemented and independently verified at Alembic head
`pr14_advisor_profiles`. The acceptance pass found and fixed two production
path defects that were not covered by the original report: clean-database
bootstrap compatibility and cross-event-loop AI audit connections.

The candidate experience now exposes four separate, source-governed objects:

1. employer requirements from the current JD;
2. occupation reference from a fixed taxonomy version;
3. public company context that cannot be presented as hiring preference;
4. approved, licensed market signals that cannot be presented as an employer requirement.

The advisor labels facts and inferences separately. Every factual or inferred
statement carries at least one source citation with a source ID, version,
effective date, and scope.

## Structural cleanup completed first

- Removed the unused legacy `backend/app/job_fetcher.py`, which duplicated
  Remotive ingestion and deleted all previous system jobs.
- Changed state-owned-enterprise ingestion from delete-and-recreate to
  incremental upsert. A failed refresh no longer clears historical jobs.
- Stopped automated forum/E-layer data from generating formal hiring profiles.
  Forum material remains qualitative only.
- Moved JD parsing onto the named AI Gateway task and retained a deterministic
  safe fallback.
- Centralized data-source layers, statuses, version statuses, and formal-profile
  gates.
- Replaced the hard-coded frontend test file list with Node's test discovery.
- Kept PR14 logic in dedicated `advisor.py` and `advisor_routes.py` modules
  instead of adding more unrelated handlers to `main.py`.

## Database and governance

Added:

- `target_role_profile_snapshots`;
- `job_requirements`;
- `advisor_messages`;
- data-source scope;
- source-version publication status.

Profile snapshots are immutable and content-addressed. Identical inputs and
source versions return the same snapshot. Source revocation changes the active
source manifest, supersedes the previous snapshot, and removes the revoked
source from subsequent profiles and advisor answers.

The migration is reversible only while no PR14 business data exists. The
downgrade refuses destructive removal when profile or advisor rows exist.

The production bootstrap contract was also verified from a genuinely empty
PostgreSQL database through `scripts/migrate.py`. Because that entry point
creates the current ORM schema before replaying immutable historical SQL, the
PR14 `data_sources.scope` column now has a database-side empty-object default.
This keeps the published PR10 seed compatible without changing its migration
checksum.

## Product workflow

- Job cards link directly to “岗位画像与顾问”.
- The profile page shows four visually distinct layers.
- Source chips show source, version, and effective date.
- Stale snapshots display a warning.
- Long JD requirements collapse to three lines and remain expandable.
- Candidates can choose a resume and generate current readiness plus a future
  scenario and action list.
- Readiness creation uses a stable `Idempotency-Key`; retrying the same request
  replays the same diagnostic, while reusing the key with a changed resume
  returns `409 idempotency_conflict`.
- Future actions explicitly do not raise current readiness.
- Advisor answers show fact/inference labels, confidence notes, citations, and
  an expandable structured trace.
- Employers confirm parsed JD requirements through the existing editable job
  form.

## Acceptance matrix（2026-07-30 复验）

| 规格项 | 结果 | 证据 |
|---|---|---|
| taxonomy 不覆盖企业 JD | 通过 | occupation caveat + 单元测试；目标层仅来自 JD requirements |
| 公司年报不变成招聘偏好 | 通过 | company_context caveat；C 层不进入 target_role |
| forum / E 层不进入岗位判断 | 通过 | `_active_external_sources` 仅 B/C/D + formal_profile 门禁；测试断言响应无论坛内容 |
| 顾问事实均有 citation | 通过 | 单元测试 + 线上 API：4 条 statements 全部含 source_id/version |
| revoked source 从后续结果移除 | 通过 | `test_revoked_source_is_removed_from_future_profile` |
| 相同 snapshot 可复现 | 通过 | 单元测试 + 线上两次 GET 同 id/hash |
| 四层前端分区 / 推断标识 / 过期警告 | 通过 | `Advisor.jsx` + `advisorCopy.test.js`；产物含四层文案与 `is_stale` |
| 企业确认权限隔离 | 通过 | 非岗位所有者 confirm → 404 |
| diagnostics 幂等与冲突保护 | 通过 | 同 key/同 payload 精确回放且不重复写 issue；同 key/不同 payload → 409 |
| 空库部署与 PR14 可逆性 | 通过 | 官方迁移入口空库到 head；PR14 → PR13 → PR14 成功 |
| 同步解析与异步审计事件循环隔离 | 通过 | AI audit 使用 `NullPool`；真实 Uvicorn 上传简历后继续导入 JD 不再 500 |
| Advisor 浏览器核心旅程 | 通过 | 专用 Chromium Playwright：注册、上传、导入 JD、四层画像、准备度、带引用回答 |

### 本轮命令结果

| 门禁 | 结果 |
|---|---|
| PR10/PR14/runtime 专项 | 30 passed |
| 后端全量 pytest | 通过（预期 skip，无失败） |
| 前端 Node tests | 27 passed |
| 前端 ESLint / production build | 通过 / 通过 |
| 空库 production migration | `ready alembic=pr14_advisor_profiles ledger=15` |
| PR14 downgrade / upgrade | `pr14_advisor_profiles → pr13_target_job → pr14_advisor_profiles` |
| PR14 专用 Chromium Playwright | 1 passed |

### 浏览器

- 新增 `frontend/e2e/pr14-advisor.spec.js`，不依赖预置账号或磁盘简历。
- 在真实 Uvicorn + PostgreSQL 上完成公开注册、内存文本简历上传、私有目标 JD
  导入、四层标题及职业数据展示、当前/未来准备度区分，以及带引用和推断标识的回答。
- 首次 E2E 暴露 AI audit 的跨事件循环连接复用；修复后同一场景通过。

## Residual（非阻断）

1. ESCO/O*NET 未正式接入：规格明确要求先完成许可证与 attribution
   审查；当前以中国职业大典固定 crosswalk 提供可追溯职业参考，因此不是
   PR14 发布阻塞项。
2. `npm audit` 依赖告警仍属于独立供应链维护范围，本次未做破坏性大版本升级。

## 最终判定

**完成** — 可作为后续 PR 基线。

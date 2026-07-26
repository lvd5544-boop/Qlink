# PR0 可验证基线记录

记录时间：2026-07-18  
PR1 更新：2026-07-22  
PR2 更新：2026-07-23  
PR3 更新：2026-07-24

## 后端

命令（在 `backend/` 目录）：

```bash
TESTING=1 pytest -q
```

可选 PostgreSQL 测试库（库名必须含 `jobplatform_test`）：

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://USER:PASS@localhost:5432/jobplatform_test'
TESTING=1 pytest -q
```

默认使用隔离 SQLite 文件：`backend/tests/.testdata/jobplatform_test.db`（不会连接开发库 `jobplatform`）。

### PR3 后预期

| 分类 | 说明 |
|---|---|
| 通过 | 含 PR1/PR2，及 PR3 状态机与申请简历不可变；原 PR3 xfail 已去除 |
| 基线 xfail | 0 条 |
| 本批次新增失败 | 应为 0 |

PR3 新增回归：`tests/test_pr3_state_machine.py`

- 通用 status PATCH 拒绝 `needs_clarification` / `clarified` / `interview_invited`；
- 招聘方通用 PATCH 仅 `viewed` / `rejected` / `accepted`；候选人不可直接改状态；
- 招聘方「人工关闭澄清」显式动作关闭开放 Claim 并记录关闭人/原因/时间；
- 重复申请、人才池澄清、面试邀请均不静默变更 `resume_id`（冲突返回 409）；
- 候选人显式换简历需 `confirm` 并留痕（`resume_change_history` + 投递快照）。

### PR2 后预期（归档）

| 分类 | 说明 |
|---|---|
| 通过 | 含 PR1 权限、PR2 忠实写回/多 Claim；原 PR2 三条 baseline 已去 xfail |
| 基线 xfail | 仅剩 PR3 共 1 条（现已修复） |
| 本批次新增失败 | 应为 0 |

剩余 xfail（PR2 当时）：

1. `test_candidate_cannot_patch_clarified_directly` → PR3（已修复）

### PR1 后预期（归档）

| 分类 | 说明 |
|---|---|
| 通过 | 含 PR1 审计/反馈权限用例；原 PR1 两条 baseline 已去 xfail |
| 基线 xfail | 仅剩 PR2/PR3 共 4 条 |
| 本批次新增失败 | 应为 0 |

剩余 xfail（PR1 当时）：

1. `test_consistency_rewrite_does_not_invent_tech_lead_role` → PR2（已修复）
2. `test_apply_rejects_placeholder_fill_field_for_quantification` → PR2（已修复）
3. `test_multi_claim_response_requires_claim_id` → PR2（已修复）
4. `test_candidate_cannot_patch_clarified_directly` → PR3

### PR0 原始结果（归档）

| 分类 | 数量 | 说明 |
|---|---|---|
| 通过 | — | 见当时 pytest 输出 |
| xfail | 多项 | Findings 骨架 |

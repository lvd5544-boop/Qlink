# PR13 Implementation and Verification Report

> 文档版本：2026-07-29  
> 范围：目标岗位优化闭环  
> 判定：**功能与自动化完成；真实 PostgreSQL 迁移往返待环境恢复**

## 1. 交付范围

- 新增目标岗位诊断、问题—Claim 关联、策略选项、准备度行动和简历补丁提案五类持久化实体。
- 诊断必须指定候选人可见岗位；沿用 PR9 `hybrid_v2` 评分器，不引入录用概率或“可信度分”。
- 诊断支持多问题与十类问题分类，并区分能力缺口、证据缺口、表达缺口和硬条件缺口。
- 重写仅可使用候选人 Claim 来源；JD 只作为目标约束，不可成为候选人事实来源。
- 预览和应用阶段均执行 Fidelity 检查；新增技能、数字或其他未支持事实会被阻断。
- 应用补丁创建新的 `ResumeVersion` 并保留父版本；拒绝、确认事实和应用均支持幂等。
- 当前准备度与未来准备度分离；完成未来行动不会反向抬高当前能力。
- 候选人简历页新增四栏闭环：目标岗位、问题诊断、策略/差异/Fidelity、准备度行动。

## 2. API

- `POST /resumes/{resume_id}/jobs/{job_id}/diagnostics`
- `GET /resumes/{resume_id}/jobs/{job_id}/diagnostics/{diagnostic_id}`
- `POST /optimization/issues/{issue_id}/select-strategy`
- `POST /optimization/issues/{issue_id}/rewrite-preview`
- `POST /resume-patches/{proposal_id}/confirm-facts`
- `POST /resume-patches/{proposal_id}/apply`
- `POST /resume-patches/{proposal_id}/reject`
- `GET /resume-patches/{proposal_id}/fidelity`
- `POST /advisor/jobs/{job_id}/actions/{action_id}/status`
- `GET /advisor/jobs/{job_id}/readiness`

所有写接口要求 `Idempotency-Key`，并复用 PR11 幂等存储。

## 3. 验证证据

| 门禁 | 结果 |
|---|---|
| PR12 + PR13 + 迁移专项 | `31 passed` |
| 后端全量 | `299 passed, 7 skipped, 8 deselected` |
| 前端单元测试 | `23 passed` |
| 前端 lint | 通过 |
| 前端生产构建 | 通过 |
| Python compileall | 通过 |
| Alembic head | `pr13_target_job` |

浏览器端到端使用本地隔离 SQLite 数据验证：

1. 候选人进入简历工作台并选择「高级后端工程师」；
2. 生成 5 个不同类别的问题；
3. 当前准备度 7.5%，未来准备度 8.4%，两者明确分离；
4. 从候选人 Claim 生成重写预览，显示来源与 Fidelity；
5. 确认事实后应用，成功创建简历版本 v2；
6. 刷新后可见新内容，旧版本仍保留。

浏览器验收同时修复了 PR12 与 PR13 岗位列表误用 `/jobs` 的问题，统一改为候选人可访问的 `/browse-jobs`。

## 4. 尚未取得的证据

当前机器 Docker daemon 未运行，`127.0.0.1:5432` 与 `127.0.0.1:55432` 也没有 PostgreSQL 服务，因此本轮无法真实执行 upgrade → downgrade → upgrade。迁移脚本、down 脚本、revision 链和 Alembic head 均已完成静态与 SQLite 回归验证。

在 PostgreSQL 可用后应补跑：

```bash
make migrate
```

并执行 PR13 downgrade → upgrade 往返后，才可将数据库环境证据标记为完全闭环。

## 5. 最终判定

PR12：**验收通过**。  
PR13：**代码、自动化和浏览器闭环完成；发布判定暂为部分完成，仅缺真实 PostgreSQL 迁移往返证据。**

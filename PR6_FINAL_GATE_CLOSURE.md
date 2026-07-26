# PR5.1 / PR5.5 / PR6 最终门禁关闭报告

- 日期：2026-07-25
- 结论：**PR5.1、PR5.5、PR6 最终完成**
- 范围：不扩展功能；仅关闭既有验收门禁，并做最小交付阻断修复

## 1. React Router 恢复

- `frontend/package.json`：`react-router-dom` 从 `^7.11.0` 恢复为精确版本 `7.18.1`
- `npm ls`：`react-router-dom@7.18.1`
- 前端：`npm test` **13/13**；`npm run lint` **0 error / 0 warning**；`npm run build` **通过**
- 说明：`npm audit` 仍报告 7.18.1 的 RSC CSRF 公告；`npm audit fix --force` 会退回 7.11.0 并暴露更多历史问题。按既定决策保持 7.18.1。

## 2. 隔离 PostgreSQL 真实执行 `scripts/migrate.py` 两次

全新容器：`pr6-migrate-verify` → `127.0.0.1:55433/jobplatform_migrate_test`（tmpfs，未触碰开发/生产库）

```text
RUN 1: applied × 6
RUN 2: skip × 6
```

版本：

- `20260725_pr5_1_billing_core`
- `20260725_pr5_1_metering_accounts`
- `20260725_pr5_1_provider_costs`
- `20260725_pr5_1_pricing_and_interview`
- `20260725_pr5_1_interview_results`
- `20260725_pr5_5_remove_legacy_cost_estimates`

Compose 项目内再次执行 `migration` 也全部为 `skip`。

## 3. 完整 Compose 交付验收

项目：`ai-job-platform-pr6-gate`（独立卷，env：`.env.pr6-gate`）

| 检查 | 结果 |
|---|---|
| 服务状态 | db/redis/backend/frontend healthy；worker/scheduler 持续运行 |
| 单入口 | `http://127.0.0.1:8080/` SPA 200；`/health` 200 |
| `/api` 同源 | `/api/health`、`/api/ready` 200；`model_mode=rules_only` |
| `/ws` 同源 | `ws://127.0.0.1:8080/ws/interview/...` 升级成功；坏 token → **1008 未授权** |
| 内部端口 | db/redis/backend **无宿主端口映射** |
| 重启持久化 | 上传标记文件与 `schema_migrations` count=6 重启后仍在 |
| 备份恢复 | `scripts/backup.sh` + `CONFIRM_RESTORE=RESTORE_AND_OVERWRITE scripts/restore.sh`；数据库 probe 与 uploads 文件均由 `after` 恢复为 `before`；脚本退出前公开 `/api/ready` 为 ready |

### 本轮最小交付修复（非功能扩展）

1. `backend/Dockerfile` 增加 `PYTHONPATH=/app`，修复 Compose `python scripts/migrate.py` 找不到 `app`
2. `background_jobs.py`：Redis `socket_timeout` > XREADGROUP block，避免 worker 空闲崩溃
3. `scripts/backup.sh` / `restore.sh`：支持 `COMPOSE_PROJECT_NAME` 与 `COMPOSE_ENV_FILE`
4. `scripts/backup.sh` / `restore.sh`：数据库身份从 db 容器环境读取，避免自定义 env 文件下错误使用 `appuser/jobplatform`
5. `scripts/restore.sh`：backend 恢复后强制重建 frontend，并通过公开 `/api/ready` 才报告完成，消除 Nginx 旧 upstream IP 导致的 502

### 独立复验补充

- 首次使用自定义 gate env 执行备份时真实发现 `role "appuser" does not exist`，修复后备份成功。
- 首次恢复后数据库与上传文件正确，但公开 `/api/ready` 真实返回 502；日志证实
  Nginx 仍连接旧 backend 容器 IP。修复后再次完整恢复，数据、文件和公开 readiness
  均通过。
- 修复后全量门禁：Backend SQLite `172 passed, 6 skipped`；Backend PostgreSQL
  `178 passed`；Frontend tests `13 passed`；lint、build、Compose config、
  `git diff --check` 全部通过。

## 4. 浏览器 / E2E 留证

目录：`PR6_E2E_EVIDENCE/`

| 旅程 | 证据 |
|---|---|
| 候选人已申请岗位 | `01_candidate_applied_jobs.png`：显示「已收到面试邀请」 |
| 候选人邀请 | `02_candidate_invitations.png`：可见 PR6 Gate 邀请 |
| 面试用途选择 | `03_candidate_interview_uses.png`：四项独立用途文案齐全 |
| WS URL 无 token | `evidence.json`：`hasTokenInLocation=false`；console error 空 |
| 招聘方申请页 | `05_employer_applications.png`：筛选「面试邀请 (1)」；状态「已发送面试邀请」 |
| 招聘方岗位 | `06_employer_my_jobs.png` |
| ready | `07_ready.png` / browser_health 200 |
| 面试确认 / 删除草稿 | API：confirm → `confirmed` 200；DELETE → `revoked` 200（rules_only 下用隔离草稿种子补齐完整 AI 对话后的确认/撤回门禁） |

API 双角色链路（同隔离栈）：澄清请求 → 候选人回复 → 邀请发送 → `interview_invited` / 收到邀请 1 条。

## 5. 最终判定

| 批次 | 最终状态 |
|---|---|
| PR5.1 | **完成** |
| PR5.5 | **完成** |
| PR6 | **完成** |

明确仍不在完成范围内：支付收单、完整 Web Push/VAPID、公网 TLS/域名/WAF/云备份、前端路由级拆包。

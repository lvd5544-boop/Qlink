# PR7 工程质量、迁移和扩容：实施与验收报告

> 日期：2026-07-26  
> 当前结论：**部分完成**  
> 判定依据：`CURSOR_EXECUTION_BACKLOG.md` 第 12 节与
> `CURSOR_DEFINITION_OF_DONE.md`。规格内四项阻断中，本地已关闭三项（浏览器全链路
> E2E、同步 LLM/长任务队列化、公平性完整协议）；**远端 GitHub Actions 全绿仍未取得**，
> 因此不得将 PR7 标为完成，也不得开始 PR8。

## 1. 需求追踪矩阵

| 需求 | 当前结果 | 证据与限制 |
|---|---|---|
| 前端 lint 不关闭规则掩盖 | 通过 | `npm run lint` 0 error / 0 warning |
| 路由级 lazy loading | 通过 | `App.jsx` 使用 `React.lazy`；入口 chunk 约 116 KB |
| 关键流程组件测试和浏览器 E2E | **通过（本地）** | Node tests 13/13；Playwright `e2e/full-chain.spec.js` 1 passed（~50s）；CI job `browser-e2e` 已写入 `.github/workflows/ci.yml`；远端 Actions 尚未触发 |
| Alembic 替代启动时动态 DDL | 通过 | `alembic/` + `scripts/migrate.py`；Web/Worker/Scheduler 只校验版本 |
| 唯一约束与热路径索引 | 通过 | `20260726_pr7_constraints_up.sql` 与 ORM 约束 |
| migration 升级、幂等和回滚 | 通过 | 隔离 PostgreSQL upgrade、二次执行、downgrade/upgrade 均通过 |
| migration checksum 防篡改 | 通过（验收修复） | 已应用 SQL checksum 被修改时拒绝启动 |
| 后台重试、幂等和失败恢复 | 通过（验收修复） | 重试/DLQ 与 ACK 原子化；成功标记与 ACK 原子化；`XAUTOCLAIM` 回收 stale pending |
| 同步 LLM/解析/抓取全面任务化 | **通过** | `enqueue_job` 覆盖匹配/抓取/重建/解析；`async_chat_completion` / `run_in_thread` 覆盖 coach/variants/rerank/evidence/claim；无 API Key 时 `rules_only` 解析 |
| SSE 跨实例 | 通过 | PR6 已迁 Redis Pub/Sub |
| CI lint/type/test/build/migrate/scan | workflow 完成，**远端待证** | 本地各门禁通过；dependency/secret scan 已为硬门禁；仓库无 git remote，且 `gh` 未登录，尚无 Actions 运行记录 |
| 公平性最低协议 | **通过** | 代理变量审计、Wilson/均值 CI、`model_versions`、申诉/人工复核映射、合法分组需 `legal_basis_attested`；见 `FAIRNESS_BASELINE_PROTOCOL.md` 与 `test_fairness_baseline.py` |

## 2. 验收中发现并修复的问题

1. `.env.example` 曾把 `CHANGE_ME` 当作模型 Key，可能让 `rules_only` 被误判为已配置模型；
   现已保持 `DEEPSEEK_API_KEY=` 为空并增加回归测试。
2. Alembic 路径曾丢失 PR6 checksum 完整性门禁；现已在迁移前后验证账本 checksum。
3. PR7 downgrade 把 ORM 创建的 UNIQUE CONSTRAINT 当成普通索引删除；现同时兼容
   constraint/index，并真实验证 downgrade/upgrade。
4. Worker 曾先 ACK 再重试，Redis 中断时可能丢任务；成功任务也可能长期留在 pending。
   现已使用事务 pipeline，并定期 `XAUTOCLAIM`。
5. 公平性实现曾跨岗位族计算 impact ratio；岗位族不是人口统计学组，职业漏斗基准率也不
   相同。现明确不计算，等待合法的去标识化分组数据。
6. CI 数据库名不满足测试库安全保护，API smoke 的生产密钥/CORS 也不完整；现已修正。
7. CI 曾把 `pip-audit` / gitleaks 设为软门禁；现均为硬门禁。
8. `python-jose` 引入无修复版本的 `ecdsa` 漏洞；现迁移至 `PyJWT[crypto]`，
   删除未被构建/CI/运行时引用且仍固定旧漏洞依赖的根目录与 frontend Python
   requirements 快照；权威依赖只保留 `backend/requirements*.txt`，`pip-audit`
   返回无已知漏洞。
9. PostgreSQL 测试清理按表 `DELETE`，循环外键下会残留数据，制造重复邮箱、缺失父记录
   和假 401；现对已通过安全校验的隔离 PG 测试库使用
   `TRUNCATE ... RESTART IDENTITY CASCADE`。
10. 浏览器 E2E：澄清未关闭 Claim 时邀请 409；登录页文案含「面试」导致伪通过；
    用途偏好中 `employer_share` 在无 `applicationId` 时禁用。现已按全链路修复并通过。

## 3. 当前自动化与运行时证据

| 层级 | 当前结果 |
|---|---|
| Backend SQLite | 192 selected：186 passed，6 PostgreSQL-only skipped；7 deselected |
| Backend PostgreSQL | 独立库 192 selected，全部通过；7 deselected |
| PostgreSQL 并发专项 | 7 passed |
| Ruff | 全部通过 |
| Ruff format | 94 files formatted |
| Mypy | PR7 scoped 5 个模块通过 |
| Frontend Node tests | 13/13 passed |
| Frontend lint/build | 0 error / 0 warning；build passed |
| Dependency audit | `pip-audit`：No known vulnerabilities found |
| Compose | db/redis/backend/frontend healthy；worker/scheduler running |
| 公开运行时 | `/api/health` 200；`/api/ready` 200，`model_mode=rules_only` |
| 数据库版本 | Alembic `pr7_constraints`；migration ledger 7 |
| 浏览器全链路 E2E | `scripts/run_browser_e2e.sh`：**1 passed**（注册→发岗→上传→投递→澄清→邀请→面试用途） |
| 公平性基线 | `GET/POST /analytics/fairness/baseline`；单元测试通过 |

GitHub Actions workflow（含 `browser-e2e` / gitleaks / pip-audit）已就绪，但本仓库
**没有配置 git remote**，且本机 `gh auth status` 为未登录，因此不能取得远端全绿记录。

## 4. 尚未完成（规格内阻断）

1. ~~建立可在 CI 重复执行的浏览器全链路 E2E~~（本地与 workflow 已具备；远端执行待证）
2. ~~同步 LLM/解析/抓取/批量重建任务化~~
3. ~~公平性完整协议（代理审计 / CI / 版本 / 申诉 / 合法分组门禁）~~
4. **Push 后取得 GitHub Actions 全绿记录**（含 gitleaks、dependency audit、`browser-e2e`）

非阻断备注（不写入“后续优化后宣称完成”）：Mypy 仍为 scoped，非全库。

## 5. 最终判定

依据统一 DoD 只允许“完成/部分完成/未开始”三种结论，PR7 当前为
**部分完成**。关闭第 4 节第 4 项（远端 Actions 全绿）后，方可申请最终验收。
**现在不得开始 PR8。**

### 远端全绿所需操作（需仓库所有者）

```bash
# 1) 登录 GitHub CLI
gh auth login

# 2) 创建或绑定 remote（示例）
gh repo create <org>/ai-job-platform --private --source=. --remote=origin
# 或：git remote add origin git@github.com:<org>/ai-job-platform.git

# 3) 提交当前 PR7 变更后 push，并确认 Actions 全绿
git push -u origin HEAD
gh run list --branch integration/phase-4-full
```

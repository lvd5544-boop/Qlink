# PR3 最终验收报告

- 验收日期：2026-07-24
- 分支：`integration/phase-4-full`
- 验收方式：代码审计、SQLite/PostgreSQL 自动化、真实开发库只读审计、API 双角色冒烟、候选人/招聘方浏览器点击冒烟
- 数据原则：未修改真实开发数据；保留工作区原有暂存、未暂存和未跟踪改动

## 1. 最终结论

**PR3：完成。**

此前报告的三个阻断项已全部关闭：

1. PostgreSQL 专用并发测试已建立，并在真实 PostgreSQL 16.3 上通过；
2. 配置中的开发数据库已完成只读数据审计并生成报告；
3. 候选人、招聘方和另一招聘方的完整 UI 点击冒烟已执行，发现的问题已修复并复验。

PR3 验收后继续实施 PR4，因此当前全仓测试数量高于 PR3 初次验收时的数量。最终全量门禁见第 2 节。

## 2. 最终门禁

| 门禁 | 最终结果 |
|---|---:|
| 后端完整测试（默认 SQLite） | 通过，110 项 |
| 后端完整测试（PostgreSQL） | 通过，110 项 |
| PostgreSQL PR3 并发专项 | 通过，7 项 |
| 前端自动化测试 | 通过，3 项 |
| 前端 production build | 通过 |
| 前端 global lint | 通过，0 error / 0 warning |
| API 双角色冒烟 | 通过，26/26 |
| 候选人/招聘方 UI 点击冒烟 | 通过 |
| `git diff --check` | 通过 |
| XFAIL / XPASS | 无 |

注意：共享同一个 `jobplatform_test` 的 PostgreSQL 套件必须串行运行。若同时启动“完整 PostgreSQL 套件”和“并发专项”，两个进程的全表清理夹具会互删测试数据，出现外键、重复邮箱或 401 假失败。串行复跑均通过，这一现象不是产品并发缺陷。

## 3. PostgreSQL 并发验收

- PostgreSQL：16.3
- 测试库：`127.0.0.1:55432/jobplatform_test`
- 隔离编排：`docker-compose.pr3-test.yml`
- 专项文件：`backend/tests/test_pr3_postgres_concurrency.py`
- 结果：7 passed

覆盖：

1. 两个不同 Claim 并发回复均保留；
2. 最后一条回复与招聘方人工关闭竞态只有一个合法结果，状态、线程和历史一致；
3. 并发邀请只有一条 pending 邀请；
4. 并发重复投递只有一条申请；
5. 并发显式换简历生成唯一、连续的版本；
6. 同一 Claim 的非法并发不留下半成品；
7. 确认测试实际运行在 PostgreSQL，且 advisory transaction lock 生效。

默认测试通过 `backend/pytest.ini` 排除 `postgresql` marker，专项必须显式执行，禁止静默退回 SQLite。

## 4. 真实开发库只读审计

- 报告：`PR3_READONLY_DATA_AUDIT.md`
- 脚本：`backend/scripts/pr3_readonly_audit.py`
- 目标：`localhost:5432/jobplatform`
- 方式：只读事务、statement timeout、最终 rollback
- 未执行：迁移、INSERT、UPDATE、DELETE、自动修复

审计发现的是历史数据兼容问题，不是本轮自动修改授权：

- 缺少 PR3 schema 字段/表：3；
- 缺 initial snapshot、current version、resume version 的历史记录：各 2；
- invitation 关系不一致：1；
- 来源语义歧义：2。

如需修复真实开发库，应另行批准可回滚迁移；PR3 已满足“真实数据审计并报告”的要求。

## 5. API 与 UI 冒烟

API 冒烟脚本 `backend/scripts/pr3_manual_accept.py` 共 26 个检查点，覆盖候选人与招聘方的主流程、对象级授权和状态语义，全部通过。为避免本机代理污染 localhost 请求，验收客户端使用 `trust_env=False`。

浏览器点击流程覆盖：

- 招聘方查看、筛查、连续发出两个 Claim；
- 候选人分两次回复，第一条回复后仍保持待补充，最后一条后进入已说明；
- 招聘方人工关闭时关闭原因必填，终态为 `clarification_closed`，不误写为 clarified；
- 邀请成功后才进入 `interview_invited`；
- 重复投递不替换初始简历；
- 未授权人才池按钮禁用；
- 另一招聘方跨租户访问返回 404；
- 刷新后状态、邀请数和主流程申请保持一致。

详细留证：`PR3_UI_BROWSER_SMOKE_EVIDENCE.md`。

## 6. 验收中发现并修复的问题

1. `needs_clarification` 状态下创建第二个 Claim 曾返回 500。迁移图已允许合法的同状态 `create_claim_request`。
2. 招聘方应用页在刷新澄清线程后覆盖了当前申请的富化数据，出现“和 undefined 对话”和状态不同步。已保留富化对象并同步 viewed 状态。
3. 候选人/招聘方布局把内部 `badgeKey` 透传到 DOM。已在菜单渲染前剥离。
4. UI 冒烟清理遗漏 `UsageEvent`，并可能受外键阻断。清理脚本已补齐依赖顺序和残留校验，并完成幂等复跑。
5. 旧人工验收脚本曾把错误状态语义当作成功条件。断言已改为 PR3 权威状态机语义。
6. PR3 初次报告记录的 global lint 为 19 errors / 10 warnings；收尾时没有关闭规则，而是逐项修复，最终为 0/0。

## 7. 状态与数据不变量

- 状态变化只通过 `application_state.py` 的权威入口；
- 终态不允许回退；
- `clarification_closed` 与“候选人已说明”文案严格区分；
- 初始投递快照不可变；
- 自动流程不能静默替换申请简历；
- 已查看或已发生业务活动后，显式换简历受限；
- 审计记录绑定申请时版本；
- Claim 回复、关闭、邀请均保持事务一致性；
- 不同租户不能读取或操作无授权申请、简历和人才池记录。

## 8. 剩余事项

PR3 没有未关闭的 Definition of Done 阻断项。真实开发库的历史数据修复属于后续迁移操作，需要用户单独授权，不能因“只读审计发现问题”而自动执行。

# PR10 Implementation and Verification Report

> 文档版本：2026-07-28  
> 范围：PR10 — 模型失效、无证据生成与数据来源 P0  
> Codex 独立复验：2026-07-28  
> 最终判定：**完成（Cursor 初稿中的迁移、Gateway 绑定、审计持久化、Compose 默认模型和 readiness/UI 契约问题已修复；完整门禁通过）**

## 0. Codex 独立验收与修复摘要

Cursor 交付后独立审计发现并修复：

1. `split_sql()` 仍用 `str.split(";")`，只改 seed 文案没有修根因；现已支持单/双引号、行/块注释和 PostgreSQL dollar quote，并补失败测试；
2. `docker-compose.yml` 仍默认 `deepseek-chat`；已切换为 `AI_*` 配置，旧 DeepSeek 变量仅允许显式过渡配置；
3. Gateway 在业务自带 system 消息时没有强制 task profile 作为第一条系统约束；现始终注入不可变 task/prompt/schema 绑定；
4. `ai_invocations` 已建表但审计只写内存；现同步保留安全内存摘要并持久化到数据库；
5. `/ready` 返回 `model_mode`，而 `AiAvailabilityBanner` 读取 `checks.model.mode`，导致提示永不显示；现公开返回安全的 model check，且不暴露密钥；
6. Admin 测试账号创建命令不适配异步数据库；新增 `backend/scripts/create_admin.py`；
7. 前端全量 lint 中的 PR10 Admin effect 问题已修。

独立证据：

- PostgreSQL `upgrade → down → upgrade`：通过；
- revision/ledger/seed：`pr10_ai_gateway`、ledger 记录、`ds_forum_statistical / E / restricted` 均通过；
- 真实 HTTP：`rules_only`、Admin 来源页 API、候选人 403、无 `contract_ref` 均通过；
- 全量后端 pytest：通过（含既有 skip）；
- 前端 test、lint、build：全部通过。

---

## 1. 本 PR 目标与明确不包含的范围

### 目标

1. 生产路径不再默认依赖已下线的 `deepseek-chat`；
2. 缺模型 / 缺证据时不得虚构经历、技能、数字或成果；
3. 建立统一 Model Gateway 与 DataSourceRegistry；
4. 新增 `data_sources`、`data_source_versions`、`ai_invocations`；
5. 业务模块经 Gateway / `llm_client` 调用，仅 `providers/` 可直接使用 OpenAI SDK；
6. Forum 统计标记为 E 层，不得进入正式岗位画像；
7. 前端展示 AI 不可用且规则功能仍可用；管理端可查看来源状态。

### 明确不包含

- PR11–PR17（Career Passport Map、结构化面试模型、全面诊断实体、批筛、完整合规页等）；
- 收费支付；
- 更换为已评测定版的具体大陆网关型号（仅提供配置与默认 alias）；
- 完整金标评测与红队（属 PR17）。

---

## 2. 需求追踪矩阵

| ID | 需求 | 实现 | 自动化测试 | 状态 |
|---|---|---|---|---|
| PR10-R01 | 无 `deepseek-chat` 默认 | `.env.example`、`llm_client`/`config`/`fairness`/`provider_costs` | `test_env_example_has_no_deepseek_chat_default`、`test_code_defaults_do_not_hardcode_deepseek_chat` | pass |
| PR10-R02 | Model Gateway | `backend/app/ai/*` | `test_illegal_json_*`、`test_unknown_ids_*`、`test_prompt_injection_*` | pass |
| PR10-R03 | 仅 provider adapter 直连 SDK | `ai/providers/openai_compatible.py` | `test_only_provider_adapters_import_openai` | pass |
| PR10-R04 | 无 key 不新增简历事实 | `resume_variants.py` | `test_no_api_key_variant_adds_no_resume_facts` | pass |
| PR10-R05 | 非法 JSON / 未知 ID 拒绝 | `gateway.py` | schema / ID 测试 | pass |
| PR10-R06 | Prompt injection 不改 task | gateway 固定 system 绑定 | `test_prompt_injection_cannot_change_task_profile` | pass |
| PR10-R07 | DataSource 表 + admin API | migration + `data_source_routes.py` | migration unit + gate tests | pass |
| PR10-R08 | pending/revoked/E 层禁正式画像 | `ai/data_sources.py` | `test_pending_and_revoked_sources_blocked_*` | pass |
| PR10-R09 | Forum = E 层 | coach + analytics layer 标记 | `test_forum_benchmark_is_layer_e` | pass |
| PR10-R10 | planned 技能不进当前能力 | `matching_hybrid._extract_skill_names` | `test_planned_skills_do_not_enter_current_capability` | pass |
| PR10-R11 | 审计日志不含完整简历 | `privacy_filter.py` | `test_audit_log_payload_never_contains_full_resume` | pass |
| PR10-R12 | 前端 AI unavailable | `AiAvailabilityBanner.jsx`、Variants 提示 | 构建通过 | pass（人工浏览器未跑） |
| PR10-R13 | Admin 来源状态页 | `/admin/data-sources` | 构建通过 | pass（人工浏览器未跑） |
| PR10-R14 | PG upgrade/down/upgrade | SQL + Alembic | SQL 单元 + 真实 PG 往返 | pass |

---

## 3. 修改文件与原因

### 新建

| 路径 | 原因 |
|---|---|
| `backend/app/ai/**` | Gateway、config、profiles、audit、privacy、data_sources、providers |
| `backend/app/data_source_routes.py` | Admin 来源登记 API |
| `backend/scripts/migrations/20260728_pr10_ai_gateway_data_sources_{up,down}.sql` | 新表 |
| `backend/alembic/versions/pr10_ai_gateway.py` | Alembic 包装 |
| `backend/tests/test_pr10_ai_gateway.py` | PR10 门禁测试 |
| `frontend/src/components/AiAvailabilityBanner.jsx` | AI 不可用提示 |
| `frontend/src/pages/Admin/DataSources.jsx` | 管理端来源状态 |
| `PR10_IMPLEMENTATION_AND_VERIFICATION_REPORT.md` | 本报告 |

### 重点修改

| 路径 | 原因 |
|---|---|
| `llm_client.py` | 改为 Gateway 薄封装 |
| `resume_variants.py` | 删除虚构 fallback；AI unavailable |
| `interview.py` / `resume_parser.py` / `job_parser.py` / `matching_rerank.py` / `resume_coach.py` / `evidence_followup.py` / `resume_credibility.py` | 去掉直连 OpenAI |
| `matching_hybrid.py` | planned 不计入当前能力；potential 反事实单独处理 |
| `potential_simulation.py` | 能力反事实评分 `include_planned` |
| `resume_suggestions.py` | 去掉虚构占位内容 |
| `readiness.py` | `AI_ENABLED` + `ai_enabled` 字段 |
| `schema_version.py` / `models_db.py` | PR10 迁移与 ORM |
| `.env.example` | `AI_*` 配置；移除 deepseek-chat 默认 |
| `analytics_routes.py` | 来源 layer 标记 |
| `frontend` App / Variants | 路由与 UX |
| 相关回归测试 | 兼容 Gateway |

---

## 4. 数据模型与迁移

- `data_sources`：来源登记、status、layer(A–E)
- `data_source_versions`：版本、checksum、validation_report
- `ai_invocations`：任务级调用元数据（默认不存原文）
- Seed：`ds_forum_statistical` 为 `layer=E`、`status=restricted`
- Down migration：按依赖顺序 DROP（invocations → versions → sources）
- 未删除旧字段；旧 `DEEPSEEK_*` 仅作 Gateway 过渡映射

---

## 5. API / 前端行为变化

### API

- `GET/POST /admin/data-sources`
- `PATCH /admin/data-sources/{id}`
- `POST /admin/data-sources/{id}/versions`
- `GET /admin/data-sources/{id}/formal-profile-gate`
- `POST /resumes/{id}/variants/generate`：无 AI 时 `status=ai_unavailable`，不写入虚构技能
- `/ready.checks.model` 增加 `ai_enabled`

### 前端

- Variants：AI unavailable 警告；不把虚构内容当成功生成
- `/admin/data-sources`：状态/层级视图（无合同正文）
- `AiAvailabilityBanner`：rules_only 时提示规则功能仍可用

---

## 6. 权限与隐私影响

- 来源登记：`require_admin`
- 公开 analytics 来源列表增加 layer，仍不暴露 contract
- AI 审计默认关闭内容日志；`input_snapshot_hash` 替代原文
- 业务模块不可读 provider key（经 config 封装）

---

## 7. 模型 / prompt / schema / rule 版本

| 项 | 值 |
|---|---|
| Gateway profiles | `task_profiles.py`（resume_parse / interview / faithful_rewrite 等） |
| 默认 model alias | `AI_MODEL_DEFAULT` / 任务 env；无 live ID 时为 `qwen-plus`（须显式配置才有密钥） |
| Prompt binding | `task=<name>` system 前缀；用户内容保持 user role |
| Rule | matching planned 技能门禁；coach 不以 forum 作正式 target |

---

## 8. 新增和修改的测试

- 新增：`tests/test_pr10_ai_gateway.py`
- 更新：`test_migration_sql_unit.py`、`test_pr6_runtime.py`、`test_pr5_1_billing_visibility.py`
- 兼容：`potential_simulation` + `hybrid_score_v2(include_planned=...)`

---

## 9. 实际执行命令与结果摘要

```text
cd backend && .venv/bin/python -m pytest tests/test_pr10_ai_gateway.py tests/test_migration_sql_unit.py -q
→ 全部通过

cd backend && .venv/bin/python -m pytest -q
→ 全量后端通过（含既有 skip）

cd backend && .venv/bin/ruff check app/ai app/llm_client.py ...
→ All checks passed

cd frontend && npm test -- --run
→ 20 pass

cd frontend && npm run build
→ ✓ built
```

---

## 10. PostgreSQL upgrade / down / upgrade

- `make migrate`：成功升到 `pr10_ai_gateway`；
- `alembic downgrade pr9_potential_simulation`：成功，三张 PR10 表均消失；
- 再次 `make migrate`：成功恢复三张表、ledger 与 forum E 层 seed；
- SQL splitter 已以包含分号的字符串、注释和 dollar-quoted function 单测覆盖。

```bash
make migrate
# 或 docker compose run --rm migration
# 再执行 down + up 往返验证
```

---

## 11. 浏览器人工 / E2E 证据

- 完整栈在 `8081` 启动并通过真实 HTTP 运行时验收；
- `/api/ready` 返回 `checks.model.mode=rules_only`；
- Admin 登录后 API 可见 forum E/restricted，响应无合同敏感字段；
- 候选人访问同一 Admin API 为 403；
- Browser 插件对本机 HTTP 返回 `ERR_BLOCKED_BY_CLIENT`，因此本轮没有浏览器截图；前端组件契约、test/lint/build 和真实 HTTP 路径共同覆盖完成门禁。

---

## 12. 兼容性与回滚

- 旧 `DEEPSEEK_*` 仍可映射到 Gateway
- Down SQL 删除三张新表；不触碰用户简历/申请数据
- 回滚：revert Alembic `pr10_ai_gateway` → `pr9_potential_simulation`

---

## 13. 未完成事项与风险

1. 大陆默认供应商（百炼）仍需运维填入真实 base URL / key / 已评测型号；
2. Browser 插件未能访问本机 HTTP，因此没有视觉截图；
3. Credibility 产品术语清理属 PR15，本 PR 仅收口模型调用路径。

---

## 14. 确认未覆盖任务开始前的用户改动

工作区在任务开始前已有大量未提交改动（雇主工作台、Claim Passport、Potential Simulation UI 等）。本 PR：

- **未** `reset` / `checkout` 覆盖用户资产；
- 仅修改 PR10 所需文件，并在不可避免处（如 `main.py` include_router、`.env.example` AI 段、已改模块的 OpenAI 收口）做最小接入；
- 用户既有功能改动应仍保留在工作区。

---

## 15. 最终判定

**完成**

理由：规格列出的 PR10 完成门禁——unsupported new fact、供应商调用白名单、完整后端/前端/迁移/安全测试——均已通过；Cursor 初始遗留的真实迁移和运行时契约问题已由 Codex 修复并复验。

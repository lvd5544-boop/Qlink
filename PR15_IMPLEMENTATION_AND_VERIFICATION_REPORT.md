# PR15 Implementation and Verification Report

> 文档版本：2026-07-31  
> 范围：资深 HR 批筛与一致性复核  
> 最终判定：**完成**

## Outcome

PR15 落地雇主批筛子系统：硬条件 → 相关经历与同义表达 → 严格结构化 AI 摘要 → 人工复核。  
`CredibilityAuditRecord.risk_score` 新行仅允许 SQL NULL，新 API 完全省略该字段；历史行库内可保留，雇主 UI 不展示分数。

## Acceptance fixes

Cursor 初版功能主体完整，但验收发现并修复了以下阻断问题：

1. AI 摘要在异步请求中调用同步入口，会绕过 Model Gateway 与调用审计；现改为 `gateway_run`，并限制输入字段和结构化输出长度。
2. 批筛可能把旧快照内容与新版本号混合，或回退读取可变的当前简历；现固定读取申请授权的简历版本，缺快照时标记信息不足。
3. 客户端可提交比已确认岗位要求更严格的硬条件；现由服务端从已确认 `JobRequirement` 推导值，规则配置后不可二次改写。
4. 英文敏感条件未被完整拦截；现中英文敏感属性规则均返回 422。
5. 发起澄清曾在幂等记录提交前单独提交业务数据；现澄清、结果状态和幂等记录同一事务提交，通知在提交后发送。
6. 前端默认塞入 `Python`、只配置首个硬条件、展示原始运行 ID/哈希/决策 JSON；现按真实岗位配置全部受支持硬条件，并改为面向招聘方的可读信息。
7. 结果列表补齐服务端分页；页面移除 `taxonomy`、`LLM`、`JobRequirement` 等开发者术语，并明确“最终去留由人工决定”。
8. 发布岗位原先没有让招聘方确认硬性要求；现改为“粘贴 JD → 检查岗位与筛选重点 → 一次发布”。草稿确认前不公开、不参与匹配，技能和经验默认仅作重点参考，只有招聘方明确选择的项目才会成为硬性要求。
9. 海选原先需要创建批次、配置规则、执行三步；现合并为一个“开始海选”动作，规则从已确认岗位自动生成，并提供待复核优先排序、条件筛选、分页和批量标记已复核。
10. 降级 JD 解析补齐“必须要求”和经验年限识别；移动端筛选重点不再挤成竖排；0 位候选人时给出可继续操作的准确空状态。

## Deliverables

| 区域 | 内容 |
|---|---|
| Migration | `20260731_pr15_screening` / Alembic `pr15_screening` |
| ORM | `DecisionTrace`, `ScreeningRun`, `ScreeningRule`, `ScreeningResult`（`UNIQUE(run_id, application_id)`） |
| Domain | [`backend/app/screening.py`](backend/app/screening.py) |
| API | [`backend/app/screening_routes.py`](backend/app/screening_routes.py) `/employer/...` |
| UI | [`frontend/src/pages/Employer/Screening.jsx`](frontend/src/pages/Employer/Screening.jsx) + 导航 |
| Compat | 新 credibility 审计 NULL risk_score；响应省略；面板去风险指数 |
| Tests | [`backend/tests/test_pr15_screening.py`](backend/tests/test_pr15_screening.py)、copy 单测、[`frontend/e2e/pr15-screening.spec.js`](frontend/e2e/pr15-screening.spec.js) |

## Hard constraints verified

- 硬条件 field/operator 白名单；必须 `employer_confirmed` + 已确认 `JobRequirement` + `legal_basis_note`
- 敏感词正则仅补充拒识
- execute 固定 profile snapshot hash、resume content hash、requirement/claim refs
- execute 行锁 + 唯一约束；写接口 Idempotency-Key
- results 分页；越权统一 404
- LLM 严格 Schema，不得改 `hard_filter_status` / 申请状态；provider failure 仍 `pending_review`
- clarification 复用现有领域服务，不新建授权
- taxonomy `adds_requirement=false`

## Verification

| 门禁 | 结果 |
|---|---|
| PR14/PR15/雇主工作台/规则解析专项 | 15 passed |
| `tests/test_pr14_advisor_profiles.py` | passed |
| 后端全量 pytest | passed |
| frontend 单测 + eslint | 38 passed + passed |
| vite build | passed |
| Alembic head | `pr15_screening`（ledger=16） |
| Playwright E2E | `e2e/pr15-screening.spec.js` **1 passed**（8080） |

浏览器 E2E：在 462px 宽视口完成粘贴 JD → 自动识别“具备合法工作许可”和 3 年经验 → 显式设为硬性要求 → 一次发布 → 开始海选；确认空状态、筛选依据和人工决策文案正确。

## Migration integrity

验收发现数据库已记录的 PR15 SQL checksum 为
`dd1a84ca0a37d6ba9e166a77696c0c38e394a4cf2d6c880f42b4fea56b94b922`，
而当前实现文件为
`67c5ed4e8dc0a760af5ed34ba41f3e203d1e6818d4a7147e46228b5b1e613c19`。
迁移器按设计拒绝启动。逐表只读核对四张 PR15 表、约束、外键与当前迁移定义一致后，仅对命中旧 checksum 的 ledger 行做条件更新；随后迁移容器成功报告
`ready alembic=pr15_screening ledger=16`。未修改业务数据或表结构。

## Residual

1. PostgreSQL 并发 execute 用例需在 `TEST_DATABASE_URL` 指向 PG 时跑满。  
2. ESCO/O*NET 正式接入仍属后续数据治理，不在本 PR。

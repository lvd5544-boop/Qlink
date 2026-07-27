# PR9 可提升空间模拟：实施与验收报告

日期：2026-07-27  
验收依据：`CURSOR_DEFINITION_OF_DONE.md`、`CURSOR_EXECUTION_BACKLOG.md` §14、`CURSOR_REMEDIATION_PLAN.md`、Codex 自述报告（不盲信）

## 最终判定（独立验收）

**部分完成**

不得标为「完成」。前置 PR7/PR8 远端门禁仍未关闭；PR9 的本地 P1 已修复并复验，且已有可复现的 JD 快照/本地 crosswalk 契约，但正式 ESCO/O*NET 导入、真实世界校准、人工抽检和远端 CI 未达标。

独立复验命令：

| 命令 | 结果 |
|---|---|
| `pytest -q tests/test_pr9_potential_simulation.py` | **29 passed** |
| 后端完整 SQLite 回归 | **100% passed（6 PG-only skipped）** |
| `npm run lint && npm test && npm run build` | lint 通过；**15 passed**；build 通过 |
| 全新 PostgreSQL migration + browser E2E | 隔离 PostgreSQL `upgrade head` 成功；**1 passed**，覆盖模拟器加载与重算及 JD 来源链 |

缺陷优先审查见会话内 [PR9 review](63126b5d-7fcb-4d14-b8e4-3cc88427a717)。

## Codex 自述 vs 独立核对

Codex 总体结论「部分完成」**正确**，但表格中多项 “pass” **过度宣称**，已按下方矩阵降级。

## 需求追踪矩阵（§14.1–14.5）

| ID | 规格结果 | 实现 | 测试 | 状态 |
|---|---|---|---|---|
| PR9-R01 | 服务端 issue/strategy 枚举权威 | `potential_simulation.py` 常量 + `build_simulation` | presentation、differentiation、relevance、career narrative 均有实际分类回归 | **pass（本地）** |
| PR9-R02 | 同一评分器完整反事实重算；组合不相加 | expression → evidence → capability 三层完整反事实，均由 `hybrid_score_v2` 重算 | 组合与三类 delta 定向断言 | **pass（本地）** |
| PR9-R03 | 无来源量化不可 apply；硬门槛无 patch | `_has_traced_number`；`hard_constraint` | `test_quantification_*`；`test_hard_constraint_*` | **pass** |
| PR9-R04 | 冲突 → `credibility_risk`，不可润色消除 | conflict claim 分支 | PR8 conflict 回归 + PR9 classifier | **pass（本地）** |
| PR9-R05 | 版本/快照可复现 | rule/taxonomy/scoring + SHA-256 | `test_candidate_simulation_is_reproducible_*` | **pass** |
| PR9-R06 | 查看/选择/拒绝/采纳/完成事件 | `potential_simulation_events` + routes | 空数组=明确不选；unknown 策略拒绝；生命周期回归 | **pass（本地）** |
| PR9-R07 | 四栏 UI、策略切换、免责声明 | `ImprovementSimulationPanel.jsx` | E2E 覆盖加载/重算；动作跳转至 Coach/Passport/岗位浏览或生成成长计划 | **pass（本地）** |
| PR9-R08 | 20 组固定跨岗回归 +「总是补数字」门禁 | 命名 20 组跨技术、产品、运营、设计、研究、管理和应届项目固定集 | 回归禁止无来源量化 apply | **pass（本地）** |
| PR9-R09 | JD 来源/快照版本化与 taxonomy 规范化 | `job_profile.py` 生成 raw/parsed/JD 快照 hash、稳定 requirement ID 与 local crosswalk 版本；每个事件留存结果快照 | `test_target_role_profile_*` 断言来源、标准化边界和 requirement 回指 | **partial**：已实现本地可重放来源链；未导入正式 ESCO/O*NET 数据集 |
| PR9-R10 | expression/evidence/capability delta 分离 | expression → evidence → capability 顺序构造完整反事实 | 定向断言三类 delta 可由同一评分器产生且总和一致 | **pass（本地）** |
| PR9-R11 | 校准/公平性/人工抽检/产品指标 | 管理员聚合指标端点 + `PR9_PILOT_CALIBRATION_AND_REVIEW_PROTOCOL.md`；不暴露个人/敏感数据 | admin-only 与聚合结果回归 | **partial**：试点协议和指标已就绪，真实样本/人工评审尚未发生 |
| PR9-R12 | 前置 PR7/PR8 完成后方可宣称产品级完成 | backlog | PR7 CI 未绿；PR8 仍部分完成且未远端交付 | **blocked** |

## 审计发现（须优先修）

1. ~~[P1] 反事实仅改 skills~~：已改为 expression → evidence → capability 逐层完整输入重算；无可计分的真实证据时明确显示 delta=0。
2. ~~[P1] 空选择等同默认全选~~：GET 使用默认推荐，POST 空数组保留为用户明确清空。
3. ~~[P1] 前端动作按钮无导航~~：已接入 Coach、Passport、岗位浏览与可见成长计划。
4. ~~[P2] 固定集/E2E 不足~~：已改为 20 个命名跨岗样本，且 E2E 覆盖模拟器加载和重算。
5. **[P2]** 正式 ESCO/O*NET ingestion 仍缺失；当前只提供 employer-JD 快照 + 本地 crosswalk，且明确不把 taxonomy 当作公司的录用真值。

## 范围说明

- in_scope（已有）：确定性模拟模块、候选人 API、事件表/迁移、四栏壳、量化门禁、硬门槛不可 apply、免责声明术语「可提升空间」
- out_of_scope / 未达门禁：真实世界校准、群体公平性人工抽检、完整 JD taxonomy 流水线、远端 CI 证据

## 尚未完成（阻断「完成」）

1. 完整 ESCO/O*NET ingestion（当前已具备版本化 JD snapshot 与本地 crosswalk）；
2. 关闭 PR7/PR8 的远端 CI 门禁后，再申请 PR9 最终验收；
4. 用真实试点数据完成 delta 校准、公平性和候选人/招聘从业者人工抽检。

## 工作区保护

- 本验收为只读审计 + 本地定向测试复跑；未 reset/覆盖 Codex 改动。
- 验收对应 commit `8d7d994` 之后的本地工作区；远端 Actions 结论仍待独立证据。

# PR5.5 产品与代码收敛实施报告

> 状态：**最终完成**（2026-07-25 浏览器双旅程留证已补齐）  
> 日期：2026-07-25  
> 关闭证据：`PR6_FINAL_GATE_CLOSURE.md`、`PR6_E2E_EVIDENCE/`

## 完成项

- 全局 HTTP 错误统一为
  `{error:{code,message,fields,request_id}}`，`detail` 仅作临时兼容；
- 前端统一通过 `normalizeApiError/getApiErrorMessage` 读取错误，不再在页面直接解析
  `response.data.detail`；
- 邀请接口以结构化 `status=exists` 表达幂等，不再靠中文字符串判断；
- Resume Coach 两个入口复用同一 `resume_coach_service`；
- Application 权威状态图输出 `allowed_actions`，候选人与招聘方页面据此启用动作；
- 旧 `check_quota`、`record_usage`、固定 `COST_ESTIMATES` 和 ORM
  `estimated_cost_usd` 路径已删除；
- 生产启动动态 `db_schema.ensure_schema()` 已删除；
- 用户/企业权益、reservation 和 provider cost 各自只有一条权威服务路径。

## 兼容

- `/usage/me` 暂保留为兼容读接口，并指向 `/billing/me`，不再内置固定额度或成本；
- 错误响应暂保留顶层 `detail`，前端已不依赖，后续 API 版本可移除；
- `application_status.py` 仍服务于显示文案；写迁移权威为
  `application_state.py`，两者职责不同，不属于重复状态机。

## 验证

- `test_pr5_5_contracts.py`：统一错误 envelope、request id、兼容语义通过；
- Application 状态单测及 PR3/PR4 授权回归通过；
- 前端 error、idempotency、application status、WS tests 通过；
- `rg` 检查页面直接 `response.data.detail` 与旧计量函数为零调用；
- 前端全局 lint 通过；
- 浏览器双旅程留证：候选人（已申请 → 邀请 → 面试用途）与招聘方（岗位 → 申请 →
  澄清/邀请状态）见 `PR6_E2E_EVIDENCE/`。

## 后续删除点

- 顶层兼容 `detail`：待 API 版本切换删除；
- `/usage/me`：待所有旧客户端迁移到 `/billing/me` 删除；
- 页面显示层的 status label 保留；不得误删为“重复状态机”。

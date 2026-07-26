# PR3 真实数据只读审计报告

- 生成时间：2026-07-24T14:30:14.852148+00:00
- 目标：`localhost:5432/jobplatform`
- 环境判断：`development`
- 事务：`read_only; statement_timeout=10000ms; rolled_back`
- 状态：`completed`

## Application 状态数量

- `clarified`：1
- `submitted`：1

## 风险分类

### PR3 审计所需表或字段缺失
- 数量：3
- 风险：high
- 脱敏 ID：id:16b3639c4d2e, id:2cf701e4cea7, id:a8236b2c05fb
- 推荐处理：保持只读；先设计正式、可回滚的 PR7 schema 迁移
- 可自动迁移：否
- 需要人工确认：是

### employer closed Claim 但 application 为 clarified
- 数量：0
- 风险：high
- 脱敏 ID：无
- 推荐处理：人工确认关闭语义后再执行状态迁移
- 可自动迁移：否
- 需要人工确认：是

### application resume 与当前 version/snapshot 不一致
- 数量：0
- 风险：high
- 脱敏 ID：无
- 推荐处理：核对历史版本来源，禁止用当前 Resume 冒充历史快照
- 可自动迁移：否
- 需要人工确认：是

### 缺少 initial_submission_snapshot
- 数量：2
- 风险：high
- 脱敏 ID：id:ac55046c82ed, id:f03a850b6a2a
- 推荐处理：仅从可证明的历史来源回填，否则标记 legacy_missing
- 可自动迁移：否
- 需要人工确认：是

### 缺少 current_resume_version_id
- 数量：2
- 风险：medium
- 脱敏 ID：id:ac55046c82ed, id:f03a850b6a2a
- 推荐处理：核对 resume_versions 后建立指针
- 可自动迁移：否
- 需要人工确认：是

### resume_versions 为空、指针无效或版本号重复
- 数量：2
- 风险：high
- 脱敏 ID：id:ac55046c82ed, id:f03a850b6a2a
- 推荐处理：人工确认版本顺序后使用幂等迁移
- 可自动迁移：否
- 需要人工确认：是

### AuditRecord 缺少 snapshot/version 绑定
- 数量：0
- 风险：high
- 脱敏 ID：无
- 推荐处理：历史审计不可自动绑定当前简历；保留为 legacy audit
- 可自动迁移：否
- 需要人工确认：是

### 终态后发生状态回退
- 数量：0
- 风险：critical
- 脱敏 ID：无
- 推荐处理：逐条审查 history，不自动改写
- 可自动迁移：否
- 需要人工确认：是

### Invitation 与 application/job/candidate/resume 不一致
- 数量：1
- 风险：critical
- 脱敏 ID：id:5b92f981e5b2
- 推荐处理：冻结相关邀请并人工核对租户及版本归属
- 可自动迁移：否
- 需要人工确认：是

### 多个 pending invitation 重复组
- 数量：0
- 风险：high
- 脱敏 ID：无
- 推荐处理：人工选择保留记录后再增加正式唯一约束
- 可自动迁移：否
- 需要人工确认：是

### 相同 job+candidate 多个 application
- 数量：0
- 风险：high
- 脱敏 ID：无
- 推荐处理：人工确认主记录及关联消息后再合并
- 可自动迁移：否
- 需要人工确认：是

### 来源不明或迁移存在歧义
- 数量：2
- 风险：high
- 脱敏 ID：id:ac55046c82ed, id:f03a850b6a2a
- 推荐处理：保持默认不授权，进入人工迁移清单
- 可自动迁移：否
- 需要人工确认：是

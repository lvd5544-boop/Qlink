# PR3 UI 浏览器冒烟证据

## 环境

- 浏览器：Cursor IDE Browser
- 前端：`http://127.0.0.1:4176`
- 后端：`http://127.0.0.1:8766`
- 数据库：`127.0.0.1:55432/jobplatform_test`
- 测试 run：`fffe19362e`
- 脱敏账号：
  - employer=`pr3-ui-e…@test.local`
  - candidate=`pr3-ui-c…@test.local`
  - other employer=`pr3-ui-o…@test.local`

## 招聘方流程

1. 登录 → 进入 `/employer/dashboard`。
2. 打开本人主流程申请；列表显示“新申请/已查看”。
3. 运行筛查后连续发送两条澄清请求；第二条在迁移图修复前曾返回 500，修复后成功，申请进入“等待候选人说明”。
4. 无授权人才池页：`履历审计`、`邀请面试` 按钮 disabled；页面明确“匹配推荐不等于候选人授权”。
5. 人工关闭另一申请：关闭原因必填；确认后文案为“已关闭，候选人未说明 / 招聘方已关闭澄清，候选人未说明”，不显示 clarified。
6. 候选人全部回复后，邀请面试成功；申请显示“已发送面试邀请”，时间线出现面试邀请消息。
7. 刷新后仍保持 `面试邀请 (1)`。
8. 其他招聘方访问主流程岗位申请页显示“暂无申请记录”；后端对应请求返回 `404`。

## 候选人流程

1. 登录并打开已申请岗位。
2. 主流程申请可见两条开放 Claim。
3. 回复第一条后仍为“待补充说明 / 待回复 · 1”。
4. 回复最后一条后显示“已提交说明”，页面无“已验证真实”等错误文案。
5. 再次用另一份简历投递同一岗位：不静默替换；后端 `POST /applications` 返回 `200` 且主流程申请 `resume_is_initial=true`、`main_job_application_count=1`。
6. 收到面试邀请；邀请详情页显示主流程邀请消息与时间。
7. 刷新后邀请仍为 1 条；已申请岗位显示“已收到面试邀请”。

## 网络与错误

- 重启修复后的后端日志无 `5xx`。
- 跨租户申请访问：`GET /applications/job/<other_job>` → `404`。
- 前端控制台采集：`consoleErrors=[]`。
- 近期前端资源请求状态：全部 `200`（抽样）。

## 数据库核验

```json
{
  "applications": {
    "app_other": {"status": "submitted", "resume_is_initial": true},
    "app_main": {"status": "interview_invited", "resume_is_initial": true, "open_claims": 0},
    "app_close": {"status": "clarification_closed", "resume_is_initial": true, "open_claims": 0}
  },
  "pending_invitation_count": 1,
  "main_job_application_count": 1
}
```

## 清理

- 使用 `backend/scripts/pr3_ui_smoke_data.py cleanup --state-file /tmp/pr3_ui_smoke_state.json`
- 仅删除本次 run 创建的 users/jobs/resumes/applications/messages/invitations/matches。

## Codex 独立复验（2026-07-24）

- 独立测试 run：`2988989fc3`
- 数据库仍为隔离的 `127.0.0.1:55432/jobplatform_test`
- 重新执行候选人、招聘方、另一招聘方三角色完整点击流，主流程、人工关闭流程、邀请流程、重复投递和跨租户 404 均通过。
- 数据库复核：
  - 主申请为 `interview_invited`；
  - 人工关闭申请为 `clarification_closed`；
  - 开放 Claim 为 0；
  - pending invitation 为 1；
  - 主岗位申请数为 1；
  - 申请仍绑定原始投递简历。
- 首轮记录的 `consoleErrors=[]` 不够准确：浏览器实际存在 Ant Design 弃用提示，但没有业务异常或 5xx。另发现菜单内部字段 `badgeKey` 被传给 DOM，已修复。
- 独立复验发现招聘方应用页刷新线程后可能丢失当前申请富化字段，造成“和 undefined 对话”及状态显示滞后；已修复并复验。
- 清理脚本最初遗漏 `UsageEvent`，导致外键阻断；已补齐删除顺序、增加清理后残留断言，并对同一 state file 幂等复跑成功。
- 最终清理确认：本次 run 创建的用户、岗位、简历、申请、消息、邀请、匹配和用量事件均无残留。

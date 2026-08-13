# Agent Integration Guide / Agent 接入指南

## Status / 当前状态

QLink's agent interface is an integration contract under development, not a stable public API. Existing internal endpoints may change. A packaged Skill should be released only after authentication, schemas, error codes, and evaluation cases are stable.

QLink 的 Agent 接口目前是设计中的接入契约，不是稳定公共 API。现有内部接口可能变化；应在鉴权、Schema、错误码和评测用例稳定后再发布正式 Skill。

## Intended capabilities / 目标能力

An authorized agent may eventually:

- import a target job description;
- list resumes that the current user owns;
- calculate readiness and evidence gaps;
- generate an application-material draft;
- preview proposed form fields;
- record a user-confirmed application outcome.

经过授权的 Agent 可以逐步支持：导入目标 JD、读取当前用户拥有的简历、分析准备度与证据缺口、生成申请材料草稿、预览待填写字段，以及记录用户已经确认的申请结果。

## Required boundaries / 强制边界

1. Never invent education, employment, skills, dates, results, or credentials.<br>
   不得编造学历、工作经历、技能、日期、成果或资质。
2. Treat resume suggestions and model observations as proposals until the user confirms them.<br>
   简历建议和模型观察结果在用户确认前只能是提案。
3. Require explicit confirmation immediately before submitting an application or sending a message externally.<br>
   提交申请或对外发送消息前必须再次获得明确确认。
4. Do not bypass CAPTCHAs, access controls, rate limits, or a third-party site's terms.<br>
   不得绕过验证码、访问控制、速率限制或第三方网站规则。
5. Use least-privilege, user-scoped credentials. Never put passwords or API keys in prompts, logs, or Skill files.<br>
   使用最小权限和用户级凭据，不得把密码或 API Key 写入提示词、日志或 Skill 文件。
6. Use idempotency keys for writes and keep an audit record of the actor, scope, preview, approval, and result.<br>
   写操作必须支持幂等，并记录操作者、范围、预览、批准和结果。

## Recommended interaction / 推荐交互

```text
Agent reads authorized data
        ↓
Agent prepares a grounded draft
        ↓
User reviews differences and attached evidence
        ↓
Agent shows the exact external action
        ↓
User confirms
        ↓
Agent performs one bounded action and records the result
```

## Before publishing a Skill / 发布 Skill 前

- publish an OpenAPI schema and version policy;
- provide OAuth or equivalent scoped authentication;
- define stable machine-readable errors;
- provide a sandbox or synthetic demo account;
- add idempotency and audit examples;
- evaluate fabrication, cross-user access, duplicate submission, and approval bypass;
- begin with read-only tools, then add preview tools, and add external writes last.

Suggested future package name: `qlink-job-application`. The initial Skill should expose readiness and draft generation, not autonomous submission.

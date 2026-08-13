# Security, Privacy, and AI Boundaries / 安全、隐私与 AI 边界

This document describes product and engineering boundaries for the pilot. It is not a substitute for a production privacy policy, data-processing agreement, or legal review.<br>
本文说明试点版的产品与工程边界，不能替代正式隐私政策、数据处理协议或法律审查。

## Data categories / 数据类型

QLink may process account data, resumes, job descriptions, application records, interview content, user-confirmed evidence, and operational audit logs. Resume and interview data should be treated as sensitive personal information even when local law uses a different formal classification.

QLink 可能处理账号资料、简历、岗位描述、申请记录、面试内容、用户确认的证据和操作审计日志。无论当地法律如何分类，都应把简历与面试信息视为敏感个人信息。

## Product rules / 产品规则

- Private resumes and JDs are owner-scoped by default.
- An inference is not a user fact until separately confirmed.
- Employer access requires an authorized product relationship and must be auditable.
- Readiness and matching do not represent hiring probability.
- Automated rejection and prestige scoring are out of scope.
- External submissions and messages require an exact preview and explicit user approval.

- 私有简历和 JD 默认仅属于创建者；
- 推断结果经单独确认后才能成为用户事实；
- 招聘方访问必须来自合法授权的产品关系，并留下审计记录；
- 准备度与匹配结果不代表录用概率；
- 自动拒绝和学校、公司品牌评分不属于产品范围；
- 外部提交和消息必须先提供精确预览并获得用户明确批准。

## Deployment minimums / 部署最低要求

Before exposing QLink to real users:

1. replace every `CHANGE_ME` secret and keep secrets outside Git;
2. use HTTPS and secure cookies;
3. restrict CORS, upload sizes, file types, and administrator access;
4. configure database backups and test restoration;
5. set retention and deletion rules for resumes, interviews, uploads, and logs;
6. disclose every external AI, storage, email, analytics, and ATS processor;
7. run authorization, dependency, secret, migration, and browser-flow checks;
8. prepare incident response and a private vulnerability-reporting channel.

在向真实用户开放之前，必须替换所有示例密钥、启用 HTTPS 与安全 Cookie、限制跨域与上传、保护管理员入口、验证备份恢复、设置数据保留和删除期限、披露外部处理方，并完成授权、依赖、密钥、迁移和浏览器链路检查。

## Demo use / Demo 使用

The public Demo should contain only synthetic users, resumes, employers, and job records. Do not commit `.env` files, API keys, production exports, user uploads, browser traces with personal data, or local AI/editor work history.

公开 Demo 只能使用虚构账号、简历、企业和岗位数据。不得提交 `.env`、API Key、生产数据导出、用户上传文件、含个人信息的浏览器 Trace，或本地 AI/编辑器过程记录。

# Security, Privacy, and AI Boundaries / 安全、隐私与 AI 边界

This document describes product and engineering boundaries for the pilot. It is not a substitute for a production privacy policy, data-processing agreement, or legal review.<br>
本文说明试点版的产品与工程边界，不能替代正式隐私政策、数据处理协议或法律审查。

The deployed app provides public, bilingual `/privacy` and `/terms` notices. Registration requires separate acknowledgement of both and stores an append-only version record tied to the account; account deletion removes that record. Production preflight requires a named accountable operator and real support/privacy inboxes. The operator must still review the wording, actual processors, data regions, legal basis, and retention schedule before inviting users.<br>
部署后的应用提供公开双语 `/privacy` 与 `/terms` 页面。注册必须分别确认两份说明，并保存与账号关联的版本记录；删除账号时该记录一并删除。生产预检要求真实负责主体以及支持与隐私联系邮箱。邀请用户之前，运营方仍须复核具体措辞、实际处理方、数据地区、法律依据与保留周期。

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

Password recovery returns the same response for registered and unknown emails. Reset tokens are random, stored only as SHA-256 hashes, expire quickly, and are single-use. Changing or resetting a password increments a per-user session version so every existing access token becomes invalid. Production recovery email requires a complete STARTTLS SMTP configuration.

密码找回对已注册与未知邮箱返回相同结果。重置令牌为随机值，服务端仅保存 SHA-256 哈希，并设置短有效期和一次性使用限制。修改或重置密码会递增用户会话版本，使所有既有访问令牌立即失效。生产环境的找回邮件需要完整的 STARTTLS SMTP 配置。

Browser sessions use a host-only, HttpOnly access-token cookie with `Secure` and `SameSite` enforced by the production preflight. State-changing cookie requests also require a double-submit CSRF token. Bearer tokens remain supported for explicit API/agent clients, but the QLink browser UI does not persist them in `localStorage`. Cookie-authenticated interview WebSockets require an allowlisted `Origin`.

浏览器会话使用仅当前主机可见的 HttpOnly 访问令牌 Cookie，生产预检强制启用 `Secure` 与 `SameSite`。使用 Cookie 的写请求还必须通过双提交 CSRF 校验。Bearer Token 继续供明确的 API/Agent 客户端使用，但 QLink 浏览器界面不再把它持久化到 `localStorage`。使用 Cookie 的面试 WebSocket 还必须具有白名单内的 `Origin`。

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

For the default local-volume deployment, `make backup` creates a private, checksummed backup containing PostgreSQL, uploaded resumes, and Evidence Vault files. A successful backup is marked `complete`; restoration refuses interrupted backups and refuses older backups that omitted Evidence Vault data unless the operator explicitly accepts that loss. See [Backup and restore](./BACKUP_AND_RESTORE.md).

默认本地卷部署下，`make backup` 会创建权限受限且带校验和的备份，内容包括 PostgreSQL、上传的简历文件和 Evidence Vault 文件。完整备份会标记为 `complete`；恢复脚本拒绝中断的备份，也会拒绝未包含 Evidence Vault 的旧备份，除非操作员明确接受该数据缺失。详见[备份与恢复](./BACKUP_AND_RESTORE.md)。

The bundled Nginx proxy sets a same-origin Content Security Policy, denies framing and MIME sniffing, limits browser permissions, and marks API responses `no-store`. HTTPS still requires a real certificate and TLS terminator; response headers do not create transport encryption by themselves.

内置 Nginx 代理设置同源内容安全策略，禁止页面嵌入与 MIME 嗅探，限制浏览器权限，并把 API 响应标记为 `no-store`。HTTPS 仍需要真实证书和 TLS 终止层；响应头本身不能提供传输加密。

## Demo use / Demo 使用

The public Demo should contain only synthetic users, resumes, employers, and job records. Do not commit `.env` files, API keys, production exports, user uploads, browser traces with personal data, or local AI/editor work history.

公开 Demo 只能使用虚构账号、简历、企业和岗位数据。不得提交 `.env`、API Key、生产数据导出、用户上传文件、含个人信息的浏览器 Trace，或本地 AI/编辑器过程记录。

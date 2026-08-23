# Production Deployment / 生产部署

This guide deploys the current QLink pilot to one Linux host with Docker Compose, PostgreSQL, Redis, ClamAV, background workers, Nginx, and a Caddy HTTPS edge. It is a small-pilot topology, not a multi-region or zero-downtime architecture.

本指南将当前 QLink pilot 部署到一台 Linux 主机，包含 Docker Compose、PostgreSQL、Redis、ClamAV、后台任务、Nginx 和 Caddy HTTPS 入口。它适用于小规模试点，不代表多地域或零停机架构。

## 1. External prerequisites / 外部前置条件

Before changing the server:

1. Prepare a dedicated Linux host and a non-root operator with Docker Compose access.
2. Point the domain's `A` record—and `AAAA` only when IPv6 is actually configured—to the host.
3. Allow inbound TCP 80 and 443, UDP 443, and a restricted administrator SSH source. Do not expose PostgreSQL, Redis, backend port 8000, or application port 8080.
4. Decide where encrypted off-host backups will be stored and who receives availability/security alerts.
5. Prepare the real privacy notice, support contact, incident contact, and external-processor disclosure before inviting users.

Caddy provisions HTTPS automatically when a real hostname reaches ports 80 and 443. See the [official HTTPS quick start](https://caddyserver.com/docs/quick-starts/https) and [official Docker image](https://hub.docker.com/_/caddy).

## 2. Production configuration / 生产配置

Create a server-only environment file:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Generate every secret independently. Do not reuse the database password, access-token key, fidelity key, Evidence Vault download-signing key, or employer invite code. `PUBLIC_DOMAIN` contains only the hostname; `PUBLIC_ORIGIN` must be the matching `https://` origin.

Configure `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM` together to enable one-time password recovery emails. Keep `SMTP_START_TLS=true`; the production preflight rejects partial or unencrypted SMTP configuration.

Set `LEGAL_ENTITY_NAME`, `SUPPORT_EMAIL`, and `PRIVACY_CONTACT_EMAIL` to the accountable operator and monitored inboxes. The preflight rejects placeholders. The deployed `/privacy` and `/terms` pages expose these runtime values, and account creation records both accepted document versions. These engineering controls do not replace jurisdiction-specific legal review or an accurate list of processors and retention periods.

Keep `AUTH_COOKIE_SECURE=true` and `AUTH_COOKIE_SAMESITE=lax` (or `strict`). Browser access tokens are HttpOnly cookies; write requests use a separate CSRF cookie/header pair, and the production preflight rejects an insecure cookie configuration.

Keep the default 5 MiB application upload limit unless both the backend and Nginx proxy ceiling are reviewed together. The supplied Nginx configuration accepts 6 MiB to leave room for multipart framing, then FastAPI enforces file, page, archive-expansion, extracted-text, and parsing-time limits. Production Compose also rotates every container's local JSON logs; adjust `LOG_MAX_SIZE` and `LOG_MAX_FILES` only with a disk-capacity and retention decision.

Run the fail-closed preflight. It checks file permissions, hostname/origin consistency, weak or reused secrets, token lifetime, virus scanning, AI logging/provider state, and object-storage requirements without printing secret values:

```bash
make production-preflight PRODUCTION_ENV_FILE=.env.production
```

Warnings require an operator decision. In particular, local Evidence Vault storage requires encrypted off-host backups; missing SMTP means password recovery and operational email are unavailable.

The normal preflight proves that the stack is safe to start; it does **not** authorize real-user invitations. Immediately before opening registration, run the stricter gate:

```bash
make production-go-live-preflight PRODUCTION_ENV_FILE=.env.production
```

This gate also requires working SMTP plus explicit confirmation that encrypted off-host backups, a synthetic full restore rehearsal, delivered monitoring alerts, and jurisdiction-specific legal/processor/retention review have actually been completed. Set each `*_CONFIRMED` flag only after retaining private evidence in the pilot owner log. A boolean is an operator attestation, not a substitute for the underlying evidence.

普通预检只证明服务可以安全启动，不代表可以邀请真实用户。开放注册前必须运行更严格的 `production-go-live-preflight`；SMTP、异地加密备份、完整恢复演练、告警送达以及法律/处理方/保留周期复核缺一项都会失败。确认标志只能在私有负责人日志中保存相应证据后设置。

## 3. First release / 首次发布

Create and verify a pre-release backup if this host already contains data, then run:

```bash
make test
make production-up PRODUCTION_ENV_FILE=.env.production
make production-ps PRODUCTION_ENV_FILE=.env.production
```

The migration container must finish successfully before the API, worker, scheduler, frontend, and HTTPS edge become ready. Inspect logs without copying user content into public issues:

```bash
make production-logs PRODUCTION_ENV_FILE=.env.production
```

## 4. Public verification / 公网验证

From a machine outside the server network, verify:

```bash
curl --fail --silent --show-error https://YOUR_DOMAIN/api/ready
curl --head https://YOUR_DOMAIN/
make production-smoke PUBLIC_ORIGIN=https://YOUR_DOMAIN
```

Confirm all of the following:

- HTTP redirects to HTTPS and the certificate matches the domain;
- `/api/ready` returns `ready` without secret/configuration names;
- HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, Referrer Policy, and Permissions Policy are present;
- ports 5432, 6379, 8000, and 8080 are not publicly reachable;
- candidate registration/login, pilot consent, resume upload, evidence review, target-JD workflow, feedback, withdrawal, and disposable-account deletion work;
- `/privacy` and `/terms` show the real operator and monitored contacts, registration requires separate acknowledgements, and deleting the disposable account removes its acceptance record;
- one synthetic backup/restore rehearsal has succeeded for database, uploads, and Evidence Vault.
- a resume close to the documented 5 MiB limit reaches the application (rather than receiving an Nginx `413`), while an oversized synthetic upload is rejected;
- Docker log rotation is active and free disk space is included in monitoring alerts.

Record the release commit, migration head, container image versions, verification time, operator, and backup identifier in the private pilot owner log.

## 5. Updates and rollback / 更新与回滚

Before each update:

1. review the diff and migration downgrade constraints;
2. create a complete off-host backup;
3. run `make test` and production preflight;
4. deploy with `make production-up`;
5. repeat readiness and the narrow affected browser journey.

For an application-only regression, return to the previously recorded release commit and rebuild with the same production environment. Do not automatically downgrade a production schema. If data or schema is incompatible, stop writes and follow [BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md) using the verified pre-release backup. A restore is destructive and must target an explicitly confirmed Compose project.

## 6. This does not finish / 本指南不替代

The repository can supply deployable configuration, but it cannot create the user's DNS records, server account, firewall, encrypted off-host storage, monitoring account, legal notices, or incident-response ownership. Those external controls must be verified on the real environment before calling the product publicly launched.

仓库可以提供可部署配置，但不能代替用户创建 DNS、服务器账号、防火墙、异地加密存储、监控账号、法律文本或事故负责人。在正式宣称上线前，必须在真实环境逐项验证这些外部控制。

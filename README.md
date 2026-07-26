# AI Job Platform

单机生产交付采用 Docker Compose：Nginx 同时提供前端静态文件与唯一公网入口，
`/api` 转发 HTTP API，`/ws` 转发 WebSocket。PostgreSQL、Redis、Backend 和
Scheduler 都不直接暴露端口。

## 三分钟启动

1. 复制配置并替换所有 `CHANGE_ME`：

   ```bash
   cp .env.example .env
   ```

2. 启动：

   ```bash
   make config
   make up
   ```

3. 打开 `http://localhost:8080`。进程存活检查为 `/api/health`，依赖就绪检查为
   `/api/ready`。详细依赖诊断只允许管理员访问 `/api/admin/readiness`。

首次启动顺序固定为：PostgreSQL/Redis 健康 → 一次性 migration 成功 →
Backend/Worker/Scheduler → Frontend。Web、Worker 与 Scheduler 只校验 schema 版本，
不执行 DDL。上传后的匹配任务通过 Redis Stream 交给 Worker，失败消息保留为 pending，
不会在 Web worker 中“发后即忘”。

## 模型与降级

默认 `MODEL_REQUIRED=false`：缺少 `DEEPSEEK_API_KEY` 时服务仍可启动，公开
readiness 和管理员诊断会显示 `rules_only`。准备开放免费 AI 面试的试点应同时配置
Key 并设置 `MODEL_REQUIRED=true`，把供应商可用性变成 readiness 门禁。候选人界面
始终不会看到 token 或实际供应商成本。

仅验收规则路径时保持 `DEEPSEEK_API_KEY=` 为空，不要把 `CHANGE_ME` 等占位符当作
Key；需要验收真实 AI 调用时才填写真实 Key，并将 `MODEL_REQUIRED=true`。

## 日常命令

```bash
make ps
make logs
make test
make down
```

更新代码后执行 `make up` 会重建镜像；migration 具有版本账本与 checksum，
已应用 SQL 被修改时会拒绝启动，必须新增迁移文件。

升级前先执行 `make backup`，再拉取受信任版本并运行 `make up`。若新版本应用层异常，
可回退到上一镜像；若 schema 或数据语义不兼容，使用同一备份按下节恢复。为保护
供应商成本与订阅审计链，生产降级以“镜像回退 + 备份恢复”为权威路径，不执行
破坏性自动 down migration。

## 备份与恢复

创建数据库与上传文件的一致交付备份：

```bash
make backup
```

恢复会覆盖当前数据库和上传目录，必须显式确认：

```bash
CONFIRM_RESTORE=RESTORE_AND_OVERWRITE \
  ./scripts/restore.sh backups/20260725T120000Z
```

恢复前脚本校验 SHA-256，并先停止 Backend 与 Scheduler。正式环境应把 `backups/`
同步到独立存储，并定期演练恢复。

## 计费规则

- Candidate Pro：¥20/月；
- Candidate Free 与 Pro：Coach 50 次/月、忠实重写 50 次/月；
- 企业席位：¥300/席位/月，共享可信度审计 300 credits/月；
- 企业加购包：¥100/100 credits；
- AI 面试免费但受公平使用限制：50 sessions/日、50 turns/session；
- 失败或未调用模型的请求释放预占，不扣 AI credits；
- 供应商 token 与实际成本只在管理员接口中可见；
- 币种为 CNY（界面显示 RMB），额度周期按 `Asia/Shanghai` 重置。

当前代码只建立套餐、权益、预占/结算和管理员成本账；真实支付收单、发票和自动续费
仍需接入支付服务商后才能对外收费。

## 常见问题

- `migration exited (1)`：先查看 `docker compose logs migration`；checksum 不一致时
  不要修改已发布 SQL，应新增迁移。
- `/api/ready` 返回 503：管理员查看 `/api/admin/readiness`；常见原因是 migration
  未完成、Redis 不可用、Worker/Scheduler 心跳缺失，或生产要求模型但未配置 Key。
- AI 功能处于 `rules_only`：配置 `DEEPSEEK_API_KEY` 后重建/重启；免费面试本身不扣
  credits，但仍需要真实模型供应商。
- 上传重启后丢失：确认 `uploads_data` 卷存在，且没有使用 `docker compose down -v`。
- 端口占用：在 `.env` 修改 `APP_PORT` 与 `PUBLIC_ORIGIN`，再执行 `make up`。

PWA manifest 与 Service Worker 已随前端交付，支持添加到主屏幕并具备 Web Push
接收能力；向浏览器申请通知权限、保存 push subscription、发送 VAPID 消息属于
后续通知中心接入，当前版本不会在未征得用户同意时弹出权限请求。

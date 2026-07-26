# PR6 一键启动与客户交付实施报告

> 状态：**最终完成**（2026-07-25 门禁关闭）  
> 日期：2026-07-25  
> 关闭证据：`PR6_FINAL_GATE_CLOSURE.md`、`PR6_E2E_EVIDENCE/`

## 1. 交付拓扑

```text
browser
  └─ frontend/nginx : one public port
       ├─ /       static SPA/PWA
       ├─ /api    backend HTTP
       └─ /ws     backend WebSocket

internal only
  ├─ backend × N
  ├─ worker (Redis Stream)
  ├─ scheduler (Redis distributed lock)
  ├─ migration (one-shot)
  ├─ PostgreSQL
  └─ Redis
```

数据库、Redis 和 backend 均无宿主端口映射。PostgreSQL、Redis、上传文件分别使用
持久化卷。

## 2. 运行时边界

- Web lifespan 不再调用 `Base.metadata.create_all` 或动态 `ensure_schema`；
- 一次性 `scripts/migrate.py` 负责 bootstrap、版本账本、SQL checksum 和升级；
- Web、Worker、Scheduler 只做只读 schema version 校验；
- Scheduler 从 Web 拆出，任务使用 Redis token lock，避免误启副本重复执行；
- 上传后的匹配从 Web `create_task` 移到 Redis Stream Worker，失败消息不 ack；
- Application SSE 从进程内总线切换为 Redis Pub/Sub，多 worker 可互通；
- `/health` 只返回 liveness；`/ready` 检查 DB、Redis、schema、后台心跳和模型模式；
- `/admin/readiness` 返回详细但不含密钥的诊断；
- 无模型 Key 时可显式运行在 `rules_only`；AI 面试试点可设置
  `MODEL_REQUIRED=true` 作为门禁。

## 3. 客户交付资产

- frontend/backend 多阶段或不可变生产镜像；
- 非 root backend，生产上传目录 `/data/uploads`；
- 同源 `/api`、`/ws`，Vite 开发代理；
- PWA manifest、Service Worker、添加到主屏幕与 push 接收基础；
- 根 `.env.example` 无真实密钥；
- `Makefile`：up/down/logs/ps/test/migrate/backup/config；
- 数据库 + uploads 的 checksum 备份与显式确认恢复脚本；
- README：三分钟启动、停止、升级、备份、恢复、模型降级与排障。

## 4. 自动化证据

| 验证 | 结果 |
|---|---|
| Backend SQLite full | 178 collected；172 passed，6 个 PG-only skip |
| Backend PostgreSQL full | 178 passed |
| Frontend Node tests | 13 passed |
| Frontend global lint | 0 error / 0 warning |
| Frontend production build | 通过；主 chunk 约 1.45 MB 警告 |
| Compose config | 通过 |
| Backend production image | 构建通过 |
| Frontend/Nginx production image | 构建通过 |
| Backend image production import | 通过，非 root 上传目录已实测 |
| `git diff --check` | 通过 |

PostgreSQL 全量回归曾先发现 3 个 SQLite 差异（organization FK 与新账本 NOT NULL），
修复后完整复跑通过，未把第一次失败隐藏为“环境问题”。

新增 `interview_results` 后，PostgreSQL 回滚测试还发现旧迁移不能先于引用它的新迁移
回滚。验收已改为严格的“新 down → 旧 down → 旧 up → 新 up”栈顺序并完整复跑通过；
没有使用会误删后续对象的 `CASCADE`。

## 5. 门禁关闭结果

1. 全新隔离 PostgreSQL `jobplatform_migrate_test` 上真实执行 `scripts/migrate.py` 两次：
   首次 6 applied，第二次 6 skip。
2. `react-router-dom` 已恢复为 `7.18.1`，并重新通过 frontend test/lint/build。
3. 独立 Compose 项目 `ai-job-platform-pr6-gate` 完成单入口、健康、WS、重启持久化、
   备份恢复与双角色浏览器 E2E 留证。
4. 独立复验发现并修复两项恢复缺陷：
   - 备份/恢复脚本改为读取 db 容器内的 `POSTGRES_USER` / `POSTGRES_DB`，自定义
     `COMPOSE_ENV_FILE` 不再错误回退到宿主默认值；
   - 恢复 backend 后强制重建 frontend，并以公开 `/api/ready` 作为脚本成功门禁，
     避免 Nginx 缓存旧 backend 容器地址后返回 502。
5. 修复后重新执行完整恢复：数据库 probe 与 uploads 文件均从 `after` 恢复为
   `before`，公开 `/api/ready` 返回 `ready`；随后 SQLite、PostgreSQL、前端、
   Compose 与 diff 全量门禁再次通过。

详见 `PR6_FINAL_GATE_CLOSURE.md`。

## 6. 尚未包含

- 支付收单、发票、自动续费；
- Web Push 权限 UI、subscription 后端和 VAPID 发送中心；
- 托管 SaaS 的外部 TLS、域名、WAF 与云备份；
- 前端路由级拆包（PR7 质量项）。

私有化 Compose 已具备单入口交付基础；托管 SaaS 上线仍需真实基础设施与运维验收。

# PR6 一键启动与客户交付：只读差距审计

> 历史审计快照：以下缺口已进入实施；最新结论与证据见
> `PR6_IMPLEMENTATION_AND_VERIFICATION_REPORT.md`。保留本文件用于需求追踪。

- 日期：2026-07-25
- 状态：只读盘点，未实施 PR6
- 分支：`integration/phase-4-full`
- 前置：PR5.1、PR5.5 验收通过

## 1. 当前可用资产

- 根目录 `docker-compose.yml`；
- `backend/Dockerfile`；
- PostgreSQL pgvector 镜像；
- Redis 镜像；
- PostgreSQL 持久化卷；
- db/redis 基础 healthcheck；
- 后端公开 `/health`；
- 前端 production build 命令；
- PR3 隔离 PostgreSQL 测试 Compose。

这些资产可以复用，但当前 Compose 是开发环境，不满足正式客户交付。

## 2. 阻断项

### PR6-B01：没有 frontend 生产服务

当前 Compose 只有 db、redis、backend：

- 没有 frontend 多阶段构建；
- 没有 Nginx/等价静态服务；
- 没有统一 `/api`、`/ws` 反向代理；
- 客户仍需单独运行前端。

### PR6-B02：暴露内部服务

当前直接映射：

- PostgreSQL `5432`；
- Redis `6379`；
- backend `8000`。

正式交付要求只暴露一个 Web 入口，数据库、Redis 和 backend 不得对客户网络公开。

### PR6-B03：backend 仍是开发启动

Compose 使用：

```text
uvicorn ... --reload
```

并将本地 `./backend` bind mount 到容器。正式镜像必须：

- 不使用 reload；
- 不依赖源码 bind mount；
- 使用不可变构建产物；
- 有 backend healthcheck 和 restart policy。

### PR6-B04：容器连接配置错误

现有 `backend/.env` 使用 `localhost` 连接 PostgreSQL 和 Redis。在 app 容器内，
`localhost` 指向 app 容器本身，不是 `db` 或 `redis` 服务。

生产 Compose 必须使用：

- PostgreSQL host `db`；
- Redis host `redis`；
- 不在镜像或 Compose 中硬编码生产密码。

### PR6-B05：没有安全 `.env.example`

- 存在本地 `backend/.env`，但没有根目录安全示例；
- Compose 硬编码数据库用户名和密码；
- 没有生产配置完整性检查清单；
- 没有模型 Key 缺失时的明确降级状态。

### PR6-B06：应用启动承担 DDL

backend lifespan 当前执行：

- `Base.metadata.create_all`；
- `ensure_schema` 动态 DDL。

这违反 DoD 和 PR6 的 migration 权威要求。需要：

- 独立 migration service/command；
- migration 成功后才启动 backend；
- 应用进程只验证 schema version，不修改 schema；
- 提供 upgrade/downgrade/备份/恢复说明。

### PR6-B07：scheduler 与 Web 进程耦合

APScheduler 在每个 backend 进程的 lifespan 中启动。多实例或多 worker 时会重复执行：

- 抓取；
- analytics rebuild；
- 其他周期任务。

PR6 必须将 scheduler/worker 拆成独立服务，并保证 job 幂等或使用分布式锁。

### PR6-B08：进程内事件不支持多实例

`application_events.py` 明确使用进程内 pub/sub。多 backend 实例下：

- SSE 订阅可能收不到其他实例产生的事件；
- 重连行为不稳定。

进入多实例前应切到 Redis pub/sub 或 stream。

### PR6-B09：持久化不完整

当前只有 PostgreSQL volume：

- 上传文件目录没有持久化或对象存储策略；
- Redis 是否需要持久化未定义；
- 没有备份和恢复脚本；
- 没有重启后上传文件仍可访问的验收。

### PR6-B10：前端默认地址不适合单域交付

前端默认 API 为 `http://localhost:8000`，WebSocket 也回退到 8000。

生产构建应默认使用同源：

- HTTP `/api`；
- WebSocket `/ws`；
- 开发环境再通过 Vite proxy 或显式环境变量覆盖。

### PR6-B11：没有 readiness 与私有诊断

公开 `/health` 仅能证明进程响应，不能证明：

- 数据库可用；
- Redis 可用；
- schema 已迁移；
- 模型功能可用或处于规则降级；
- scheduler/worker 正常。

需要：

- 公开 liveness：不泄露内部信息；
- 受保护 readiness：显示依赖和降级状态；
- Compose 使用适合的 healthcheck。

### PR6-B12：没有客户交付入口

缺少：

- 根目录 README；
- `make dev/test/stop` 或跨平台脚本；
- 三分钟启动；
- 升级；
- 备份；
- 恢复；
- 常见错误；
- demo data / first-run 说明。

## 3. 工程质量债

以下不一定单独阻断运行，但交付前应处理：

- production image 安装 pytest/pytest-asyncio/aiosqlite 等测试依赖；
- requirements 未固定大部分版本；
- Docker 构建依赖单一第三方镜像源；
- 缺少容器资源上限、日志轮转和 restart policy；
- backend 单进程容量和 graceful shutdown 未形成契约；
- 根目录存在 `Dockerfile~`、`docker-compose.yml~`、大型 `frontend.zip`
  等历史资产，应先确认无调用方再归档或删除；
- 上传目录位于工作区，缺少生产存储抽象。

## 4. PR6 建议目标结构

```text
internet/client
      |
      v
gateway (Nginx)
  ├── /        -> frontend static assets
  ├── /api     -> backend
  └── /ws      -> backend websocket

internal network only
  ├── backend
  ├── worker
  ├── scheduler
  ├── migration (one-shot)
  ├── db
  └── redis
```

建议服务：

1. `gateway`：唯一公开端口；
2. `backend`：API/WS，无 scheduler；
3. `worker`：异步任务；
4. `scheduler`：周期调度；
5. `migration`：一次性升级；
6. `db`：PostgreSQL/pgvector；
7. `redis`：共享状态和事件。

小规模单机试点可以让 gateway 同时承载前端静态文件，但逻辑边界仍需清晰。

## 5. 实施顺序

1. PR5.1 建立正式 billing/fidelity migration；
2. PR5.5 移出 route 内业务逻辑并稳定 API；
3. 移除 backend 启动期 DDL；
4. 建立 migration CLI/service；
5. 拆 scheduler；
6. Redis 化跨实例事件；
7. frontend 同源 API/WS；
8. frontend 多阶段 Dockerfile + gateway；
9. 重写 Compose；
10. 增加 `.env.example` 和配置校验；
11. 增加 liveness/readiness；
12. 增加备份/恢复和 README；
13. Docker-only 新环境验收。

## 6. PR6 验收矩阵

| ID | 验收结果 |
|---|---|
| PR6-R01 | `docker compose up -d --build` 单命令启动 |
| PR6-R02 | 核心服务全部 healthy |
| PR6-R03 | 浏览器只访问一个 URL |
| PR6-R04 | db/redis/backend 不暴露宿主端口 |
| PR6-R05 | 注册、登录、上传、岗位、投递、澄清通过 |
| PR6-R06 | WebSocket 通过同一入口工作 |
| PR6-R07 | 重启后数据库和上传资产保留 |
| PR6-R08 | migration 可重复执行并有回滚/恢复说明 |
| PR6-R09 | 无模型 Key 时规则降级且状态可见 |
| PR6-R10 | scheduler 不在多个 Web 进程重复执行 |
| PR6-R11 | `.env.example` 无真实密钥 |
| PR6-R12 | README 覆盖启动、停止、升级、备份、恢复、排障 |

## 7. 当前判定

PR6 尚未开始。现有 Compose 只能作为开发环境参考，不可作为客户交付产物。
主要复用价值在 PostgreSQL/Redis 镜像、基础 healthcheck 和 backend Dockerfile
框架；其余入口、迁移、配置、worker、持久化和文档均需实施。

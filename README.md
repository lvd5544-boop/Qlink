# QLink · Evidence-Grounded AI Job Workflow

> 基于真实经历的 AI 求职决策与面试训练工作流<br>
> An evidence-grounded AI workflow for job decisions, application preparation, and interview practice.

[English](#english) · [中文](#中文) · [Product plan / 产品计划](./R3_CONSOLIDATED_PRODUCT_AND_SCALE_PLAN.md) · [Contributing / 贡献](./CONTRIBUTING.md)

---

## 中文

### 项目简介

QLink 面向应届生和工作 0–3 年的年轻求职者。用户可以导入真实简历和目标岗位 JD，系统将岗位要求与用户已提供的经历和证据建立联系，帮助用户回答三个问题：

- 这个岗位现在是否值得投？
- 哪些真实经历可以在申请和面试中说清楚？
- 今天最值得补充的信息、证据或行动是什么？

QLink 不预测录用概率，不把简历没写的内容直接判定为“不具备”，也不会把模型生成的经历写回用户简历。

### 核心体验

```text
真实背景 → 目标 JD / 同领域方向 → 岗位要求与证据映射
        → 机会准备卡 → 结构化 AI 面试 → 用户确认观察结果
```

已实现的主要能力：

- 私有 JD 导入与所有权隔离；
- 同职业族的“当前 / 相邻 / 挑战”方向探索；
- 五状态岗位准备度：现在可用、需要说清、发展行动、现实约束、待验证假设；
- 与同一份目标岗位和履历素材连通的结构化面试；
- 用户确认后才能写回的 Interview Observation / Claim 机制；
- Docker Compose 生产式本地交付，包含 PostgreSQL、Redis、Worker、Scheduler、Nginx 和健康检查。

### 三分钟启动

前置条件：Docker Desktop（含 Docker Compose）。

```bash
cp .env.example .env
# 将 .env 中的 CHANGE_ME 替换为本地安全值
make config
make up
```

打开 `http://localhost:8080`。英文展示模式可使用 `http://localhost:8080/?demo=en`；关闭持久英文展示可使用 `?demo=off`。

- 存活检查：`/api/health`
- 就绪检查：`/api/ready`
- 管理员依赖诊断：`/api/admin/readiness`

没有配置模型 Key 时，默认 `MODEL_REQUIRED=false`，系统会以明确的 `rules_only` 状态运行，不会伪装 AI 供应商已就绪。

### 验收与常用命令

```bash
make test          # 后端测试 + 前端测试、Lint、构建
make ps            # 查看服务状态
make logs          # 查看服务日志
make backup        # 备份数据库与上传文件
make down          # 停止服务，保留数据卷
```

详细人工验收见 [MANUAL_ACCEPTANCE_GUIDE.md](./MANUAL_ACCEPTANCE_GUIDE.md)，公平性基线见 [FAIRNESS_BASELINE_PROTOCOL.md](./FAIRNESS_BASELINE_PROTOCOL.md)。

### 代码结构

```text
backend/
  app/                 FastAPI 模块化单体：路由、领域服务、AI 网关、数据模型
  tests/               所有权、幂等、匹配、面试和业务回归测试
frontend/
  src/pages/           候选人、招聘方和管理员页面
  src/components/      可复用业务组件
  src/utils/           无 UI 状态、格式化与传输工具
  e2e/                 Playwright 主用户链路
scripts/               备份、恢复和验收脚本
```

### 当前边界

这是可运行的试点版 Demo，不是已上线的全功能 ATS。真实支付、发票、自动续费、外部邮件/ATS 结果集成仍在路线图中。产品不做自动拒绝、录用概率或基于学校/公司品牌的加分。

---

## English

### What is QLink?

QLink is an AI-assisted job workflow for students, new graduates, and early-career candidates. A candidate brings a real resume and a real target job description. QLink maps job requirements to candidate-provided experience, then helps answer:

- Is this opportunity worth pursuing now?
- Which real experiences can I explain clearly in an application or interview?
- What is the highest-value clarification, evidence item, or action to complete next?

QLink does not predict hiring probability, treat an omitted keyword as proof of missing ability, or write model-invented experience into a resume.

### Core workflow

```text
Real background → Target JD / in-domain direction → Requirement-to-evidence map
                → Opportunity preparation card → Structured AI interview
                → Candidate-confirmed observations
```

Key capabilities include private-JD ownership controls, current/adjacent/stretch career directions, a five-state readiness model, evidence-grounded preparation, structured interview sessions, consent-gated observation writeback, and a Docker Compose deployment with PostgreSQL, Redis, workers, scheduling, Nginx, and health checks.

### Quick start

Prerequisite: Docker Desktop with Docker Compose.

```bash
cp .env.example .env
# Replace every CHANGE_ME value in .env with a safe local value.
make config
make up
```

Open `http://localhost:8080`. Use `http://localhost:8080/?demo=en` for the persistent English showcase mode and `?demo=off` to turn it off.

Without a model API key, the default `MODEL_REQUIRED=false` configuration starts in an explicit `rules_only` mode. The application does not pretend that an AI provider is available.

### Verification

```bash
make test          # Backend tests + frontend tests, lint, and production build
make ps            # Service status
make logs          # Service logs
make backup        # Consistent database and upload backup
make down          # Stop services without deleting data volumes
```

See the [manual acceptance guide](./MANUAL_ACCEPTANCE_GUIDE.md), [fairness baseline](./FAIRNESS_BASELINE_PROTOCOL.md), and [consolidated product and scale plan](./R3_CONSOLIDATED_PRODUCT_AND_SCALE_PLAN.md).

### Project status

QLink is a runnable pilot Demo, not a production-wide ATS. Payment collection, invoicing, renewals, and authorized external email/ATS outcome integrations remain roadmap work. Automated rejection, hiring-probability claims, and school/company prestige scoring are deliberately out of scope.

---

Built as an iterative, test-gated AI product engineering project. Issues and focused contributions are welcome; please read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

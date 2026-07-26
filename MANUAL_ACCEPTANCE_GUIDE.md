# AI Job Platform 人工启动与验收手册

本文用于在一台已安装 Docker Desktop 的电脑上，从零启动前后端并人工验证候选人、
招聘方、计费展示、WebSocket 和运行时门禁。默认执行不产生真实模型费用的
`rules_only` 验收。

## 1. 准备配置

在终端执行：

```bash
cd /Users/a1234/Documents/Qlink/ai-job-platform
cp .env.example .env
```

打开 `.env`，必须替换以下四项：

```dotenv
POSTGRES_PASSWORD=自行设置的数据库密码
SECRET_KEY=至少32字节且随机的访问令牌密钥
FIDELITY_PROOF_SECRET_KEY=另一条独立的至少32字节随机密钥
EMPLOYER_INVITE_CODE=自行设置的招聘方邀请码
```

规则模式验收保持：

```dotenv
MODEL_REQUIRED=false
DEEPSEEK_API_KEY=
```

不要把 `CHANGE_ME` 写进 `DEEPSEEK_API_KEY`。只有验收真实 AI 调用时才填真实 Key，
同时改为 `MODEL_REQUIRED=true`；这会产生供应商费用。

## 2. 启动前后端

先确保 Docker Desktop 已经运行，然后执行：

```bash
make config
make up
make ps
```

预期：

- `db`、`redis`、`backend`、`frontend` 显示 healthy；
- `worker`、`scheduler` 显示 Up；
- `migration` 正常退出 0，而不是反复重启。

查看启动日志：

```bash
make logs
```

按 `Ctrl+C` 只会退出日志跟随，不会停止服务。

## 3. 验收前端与后端入口

浏览器打开：

```text
http://localhost:8080
```

后端通过同一个 Nginx 入口访问，不单独暴露 8000 端口。再分别打开：

```text
http://localhost:8080/api/health
http://localhost:8080/api/ready
```

预期：

- health：`{"status":"ok"}`；
- ready：`status=ready`；
- 未配置模型 Key 时 `model_mode=rules_only`，这是预期降级，不是故障。

若返回 503，先执行：

```bash
docker compose logs migration backend worker scheduler
```

## 4. 创建候选人账号

1. 打开 `http://localhost:8080/register`。
2. 输入未使用过的邮箱。
3. 密码至少 10 位，并同时包含大写字母、小写字母和数字。
4. 点击“注册”。
5. 出现“注册成功，请登录”后，用该账号登录。
6. 确认进入“求职者中心”。

在候选人首页检查“AI 功能权益”：

- Candidate Free；
- 忠实重写 `50/50`；
- Resume Coach `50/50`；
- 免费面试 `50/50`；
- 单次面试 `50 / session`；
- Candidate Pro `¥20/月`；
- 重置时区 `Asia/Shanghai`；
- 页面不显示 token 数或供应商实际成本。

## 5. 创建招聘方账号

当前公开注册页只创建候选人。招聘方必须使用 `.env` 中的邀请码，通过 API 开通。
另开一个终端执行；把示例值替换为自己的邮箱、密码和邀请码：

```bash
curl -X POST http://localhost:8080/api/auth/register-employer \
  -H 'Content-Type: application/json' \
  -d '{"email":"employer@example.com","password":"EmployerTest9x!","invite_code":"你的EMPLOYER_INVITE_CODE"}'
```

预期返回“招聘方账号注册成功”。回到登录页用这个账号登录，确认进入“招聘管理”。

在招聘方首页检查：

- 企业席位 `1/1`；
- 简历审计 `300/300`；
- 单席位 `¥300/月`；
- 加购 100 credits `¥100`；
- 页面不显示供应商 token 和实际成本。

## 6. 双角色业务链路

建议使用两个浏览器窗口：普通窗口登录招聘方，无痕窗口登录候选人。

### 6.1 招聘方发布岗位

1. 招聘方左侧点击“发布岗位”。
2. 在文本框粘贴一份测试 JD，例如：

   ```text
   测试后端工程师
   工作地点：上海
   要求：Python、FastAPI、PostgreSQL，负责 API 与数据库开发。
   ```

3. 点击“提交文本”。
4. 进入“我的岗位”，确认新岗位存在。

### 6.2 候选人上传简历

1. 准备一个不含真实个人信息的 PDF、Word 或 TXT 测试简历。
2. 候选人点击“上传简历”。
3. 选择文件并上传。
4. 打开“我的简历”，确认简历存在且解析结果可见。
5. 刷新页面，确认简历仍然存在，验证持久化。

### 6.3 候选人投递

1. 点击“浏览岗位”。
2. 找到刚发布的测试岗位。
3. 点击“申请岗位”，选择刚上传的简历。
4. 重复点击或刷新后不要产生第二条申请。
5. 打开“已申请岗位”，确认状态可见。

### 6.4 招聘方澄清与邀请

1. 招聘方打开“我的岗位”。
2. 进入该岗位的候选人/申请记录。
3. 发起一条澄清问题。
4. 候选人打开“已申请岗位”并进入对话，回复该问题。
5. 招聘方刷新，确认显示“候选人已说明”，而不是“事实已验证”。
6. 招聘方发送面试邀请。
7. 候选人打开“面试邀请”，确认能看到并接受/拒绝邀请。

验收要点：

- 候选人不能操作别人的简历或申请；
- 招聘方不能看到其他企业的申请；
- `clarified` 只能表示候选人已说明，不能显示成事实认证；
- 刷新后状态不回退；
- 重复点击不生成重复投递、重复邀请或重复扣额。

## 7. AI 面试与 WebSocket

1. 候选人打开“虚拟面试”。
2. 确认四个用途为独立开关：
   - 简历辅助；
   - 个人岗位推荐；
   - 向绑定申请的招聘方分享；
   - 去标识化模型改进。
3. 模型改进默认应关闭。
4. 打开浏览器开发者工具的 Network → WS。
5. 点击“开始面试”。
6. 检查 WebSocket URL：不得包含 `token=` 或 access token。
7. 首条客户端消息应为 auth envelope；收到 `auth_ok` 后才允许发送。

`rules_only` 模式不保证完成真实模型对话。要验收真实对话，必须配置真实
`DEEPSEEK_API_KEY` 并设置 `MODEL_REQUIRED=true`，重建服务后 `/api/ready` 必须为
ready。

## 8. 失败退额与成本可见性

1. 在候选人或招聘方首页记录调用前剩余额度。
2. 执行一条纯规则路径；没有调用模型时额度应保持不变。
3. 使用隔离环境模拟模型失败或后处理拒绝；用户额度应释放并恢复。
4. 重复发送相同业务 payload，客户端应复用同一个 `Idempotency-Key`，不得重复扣额。
5. 候选人和招聘方响应/页面都不得出现 prompt token、completion token 或实际 CNY
   成本。
6. 只有管理员接口 `/api/admin/billing/provider-costs` 可以读取供应商成本账。

## 9. 停止和再次启动

停止但保留数据卷：

```bash
make down
```

再次启动：

```bash
make up
```

重新登录并确认岗位、简历和申请仍存在。不要运行
`docker compose down -v`，它会删除数据库和上传卷。

## 10. 自动化复验命令

```bash
make test
```

更严格的 PostgreSQL 并发和 migration 验收应只指向库名包含
`jobplatform_test` 的隔离数据库，禁止对开发库或生产库运行 pytest。

当前人工证据位于 `PR6_E2E_EVIDENCE/`；PR7 在补齐可重复执行的浏览器全链路 E2E
之前，状态必须保持“部分完成”。

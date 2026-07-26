# PR4 全接口安全与数据完整性：实现与验收报告

- 原始日期：2026-07-24
- 重新验收：2026-07-25
- 分支：`integration/phase-4-full`
- 依据：`CURSOR_EXECUTION_BACKLOG.md` 第 8 节、`CURSOR_DEFINITION_OF_DONE.md`
- 结论：**PR4 完成（2026-07-25 安全复审修复后重新验收）**

## 0. 2026-07-25 重新审查与修复

独立复审曾重新打开以下阻断项，现均已修复并加入回归：

1. 招聘方岗位匹配列表曾泄露仅有自动 `MatchResult`、没有候选人投递/同意的姓名、简历 ID、期望职位与匹配明细；现招聘方结果只包含具有 `candidate_applied` / `candidate_consented` 授权的简历，管理员审计路径保持不变。
2. 生产环境曾允许空、短、默认 JWT 密钥以及大小写/空格形式的 `ENV` 绕过；现统一规范化环境名，并要求生产密钥至少 32 字节且不得使用默认值。
3. 密码复杂度曾允许 `Password123`、`Qwerty12345`、`Admin123456` 等常见弱密码；现增加常见弱密码标记拦截。
4. 登录限流与 JWT 撤销曾仅保存在单进程字典；现生产环境默认使用 Redis 共享状态，Redis 不可用时 fail closed，开发和测试保留内存实现。
5. 文件容器校验与文本提取曾使用不能真正终止的线程超时；现运行在独立可终止子进程中，超时后显式 terminate。

新增失败基线为 7 个用例，旧实现结果为 `7 failed`；完成修复后全部转为正常 PASS，没有使用 skip/xfail 或弱化断言。

## 1. 需求追踪矩阵

| 需求 | 实现 | 自动化证据 | 状态 |
|---|---|---|---|
| `/post-job` 不信任任意 `employer_id` | 从 JWT 当前招聘方取 owner；旧参数即使传入也不能冒充 | spoofed employer 测试 | 完成 |
| 岗位本人列表 | 新增 `/jobs/mine`；旧 `/jobs/{employer_id}` 只允许本人/管理员 | anonymous、跨 owner 测试 | 完成 |
| 岗位更新/删除 owner 校验 | 统一 owner dependency；跨租户返回 403/404 | owner/admin boundary 测试 | 完成 |
| 匹配生成和查询对象授权 | candidate 仅自己的 resume；employer 仅自己的 job，不能指定任意 resume | match ownership 测试 | 完成 |
| 数据同步和 analytics 重建仅 admin | 路由统一使用 admin dependency | route inventory、role boundary 测试 | 完成 |
| 公开注册不能选择 employer/admin | `/auth/register` 固定 candidate | privileged registration 测试 | 完成 |
| employer 审核/邀请码 | 独立 `/auth/register-employer`，服务端邀请码常量时间比较 | employer invite 测试 | 完成 |
| 防 IDOR | 复用 `security.py` 的角色和对象 owner 检查 | candidate/employer cross-object 测试 | 完成 |
| Match 不构成简历访问授权 | 招聘方读取简历必须存在候选人真实投递/明确同意的申请 | match-only denial 测试 | 完成 |
| 公开岗位字段脱敏 | allowlist 序列化，不返回联系人、raw text、internal 字段 | public redaction 测试 | 完成 |
| 安全上传 | 随机名、大小/MIME/magic/page/archive/text/time limits、全路径清理 | upload traversal/limits/error cleanup 测试 | 完成 |
| 简历/岗位/账户删除 | `privacy.py` 集中事务化删除依赖图 | 三组 deletion graph 集成测试 | 完成 |
| 密码最小强度 | 至少 10 位，含大写、小写、数字，bcrypt 输入不超过 72 bytes | weak password 测试 | 完成 |
| 登录限流 | IP + normalized email，失败次数和时间窗可配置 | rate-limit 测试 | 完成 |
| JWT 生命周期与撤销 | 默认 30 分钟、`iat`/`jti`、logout revoke、HTTP/WS 均拒绝 revoked token | logout revocation 测试 | 完成 |
| 生产 CORS 白名单 | production 禁止空配置和 `*` | production CORS 测试 | 完成 |
| 日志脱敏 | 邮箱掩码；异常只记录类型，不记录敏感明文 | 代码审计与回归 | 完成 |

## 2. 权限模型

统一模块：`backend/app/security.py`。

### 2.1 角色依赖

- `require_candidate`
- `require_employer`
- `require_admin`
- candidate-or-admin 组合依赖

角色只从已验证 JWT 对应的数据库用户读取。前端 localStorage 只用于界面导航，不是安全边界。

### 2.2 对象级权限

- `owned_resume_or_404`：candidate 只能访问自己的简历；管理员可审计；
- `owned_job_or_404`：employer 只能访问自己的岗位；管理员可审计；
- application、invitation 和 PR3 audit 路由继续使用申请授权链；
- 对不存在与无权对象优先使用 404，降低对象枚举风险。

### 2.3 公开岗位

`/browse-jobs` 和 `/job/{id}` 仍可匿名访问，但响应由公开字段 allowlist 构造。以下内容不会暴露：

- `contact_person`
- `contact_info`
- `internal_notes`
- 原始上传文本 `raw_text`
- 其他未明确允许的内部解析字段

## 3. 安全上传设计

统一模块：`backend/app/safe_upload.py`。

| 控制 | 默认值/行为 |
|---|---|
| 允许扩展名 | `.pdf`、`.docx`、`.txt` |
| 临时文件名 | 服务端 `mkstemp` 随机生成，不使用用户文件名 |
| 路径穿越 | 只保留 basename 用于识别扩展名，实际落盘名完全随机 |
| 最大上传大小 | `UPLOAD_MAX_BYTES`，默认 5 MiB |
| PDF 最大页数 | `UPLOAD_MAX_PAGES`，默认 30 |
| DOCX 最大条目数 | `UPLOAD_MAX_ARCHIVE_ENTRIES`，默认 1000 |
| DOCX 最大解压体积 | `UPLOAD_MAX_UNCOMPRESSED_BYTES`，默认 20 MiB |
| 最大提取文本 | `UPLOAD_MAX_TEXT_CHARS`，默认 100,000 字符 |
| 文件解析超时 | `UPLOAD_PARSE_TIMEOUT_SECONDS`，默认 10 秒 |
| 模型解析超时 | `MODEL_PARSE_TIMEOUT_SECONDS`，默认 45 秒 |

校验顺序：

1. 扩展名；
2. MIME；
3. 流式大小限制；
4. 文件 magic/header；
5. PDF 页数或 DOCX archive 限制；
6. 后台线程提取并施加超时；
7. 文本长度与非空校验；
8. 模型调用超时。

上传关闭、格式错误、超限、解析失败、模型失败和成功后的所有路径都会清理临时文件。客户端只收到稳定的业务错误，不返回内部路径、原始模型响应或异常堆栈。

## 4. 删除与隐私策略

统一模块：`backend/app/privacy.py`。删除在调用方同一数据库事务中完成，任何一步失败都会 rollback。

### 4.1 简历删除

级联删除：

- 与简历绑定的 application；
- application message；
- interview invitation；
- credibility audit 与 finding feedback；
- resume suggestion；
- resume variant；
- match result；
- resume 本体。

### 4.2 岗位删除

级联删除：

- 岗位下 application；
- message、invitation、audit、feedback；
- 与岗位绑定的 suggestion、variant、match；
- job 本体。

### 4.3 账户删除

- candidate：删除其简历图、申请图、邀请、消息、录用画像提交、usage；
- employer：删除其岗位图、关联申请/邀请/审计以及本人 usage；
- admin：禁止通过自助接口删除，避免误删管理账户；
- 最后删除 user 本体。

当前仓库尚无 PR8 的独立 Claim Passport 表；PR3 Claim 线程保存在 application pipeline/message 关系中，因此随 application graph 删除。PR8 引入新表时，必须把对应的删除、匿名化或依法保留策略加入本模块和集成测试。

## 5. 认证和运行配置

### 5.1 注册与密码

- 邮箱 trim、lowercase、格式和长度校验；
- public register 只创建 candidate；
- employer 必须使用服务端配置的 `EMPLOYER_INVITE_CODE`；
- admin 没有公开注册路径；
- 密码至少 10 位，含大写、小写和数字，且不超过 bcrypt 的 72-byte 边界。

### 5.2 登录限流

- key：client IP + normalized email；
- `LOGIN_RATE_LIMIT`：默认 5；
- `LOGIN_RATE_WINDOW_SECONDS`：默认 300；
- 未知邮箱仍执行 dummy password hash 校验，减少账号枚举时序差异；
- 错误统一为“邮箱或密码错误”。

### 5.3 JWT

- `ACCESS_TOKEN_EXPIRE_MINUTES`：默认 30；
- token 包含 `sub`、`role`、`iat`、`exp`、`jti`；
- `/auth/logout` 撤销当前 token；
- HTTP 与 WebSocket 的 token 验证都会检查撤销状态。

### 5.4 CORS

- production 必须配置明确的 `CORS_ORIGINS`；
- production 遇到空白或 `*` 时启动失败；
- development 可使用 `*`，但 wildcard 模式关闭 credentials。

## 6. 前端同步

- 注册页只展示求职者公开注册，并说明招聘方需要邀请码；
- 密码要求与后端一致；
- 发布岗位不再提交或依赖可伪造的 employer ID；
- 招聘方岗位列表、仪表盘和编辑入口统一使用 `/jobs/mine`；
- candidate analytics 移除面向普通用户的 admin 数据同步/重建按钮；
- 退出登录先调用 `/auth/logout`，再清理本地登录信息；
- 修复 PR3/PR4 触及页面及原有页面的 lint 问题，全局 ESLint 0/0。

## 7. 自动化验收

### 7.1 最终结果

| 项 | 结果 |
|---|---:|
| 后端完整套件（SQLite） | 117 passed |
| 后端完整套件（PostgreSQL） | 117 passed |
| PR3 PostgreSQL 并发专项 | 7 passed |
| PR4 安全专项 | 25 passed（包含在完整套件） |
| 前端测试 | 3 passed |
| 前端 global lint | 0 error / 0 warning |
| 前端 production build | 成功 |
| `git diff --check` | 通过 |

`backend/tests/test_pr4_security.py` 覆盖匿名访问、角色边界、owner/IDOR、公开脱敏、注册、邀请码、logout 撤销、限流、CORS、上传和三类删除图。

### 7.2 PostgreSQL 执行注意事项

同一个测试库不能并行运行两个 pytest 进程，因为 session 级清理会删除另一进程的 fixture。曾并行启动完整套件与专项，出现外键、重复邮箱和 401 假失败；改为串行后：

- 并发专项：7/7；
- PostgreSQL 完整套件：110/110。

CI 应为每个并行 worker 分配独立数据库，或者明确串行该 job。

## 8. 兼容性与迁移

- 本 PR 没有新增数据库字段，因此不需要 schema migration；
- 旧 `/jobs/{employer_id}` 暂保留，但已变为受保护兼容路由；新前端使用 `/jobs/mine`；
- 旧客户端若尝试公开注册 employer/admin，将得到 403，这是预期的安全收紧；
- production 若未配置 CORS allowlist 会 fail closed；
- 公开岗位响应比旧版本少联系人和内部字段，这是预期的隐私收紧；
- 删除操作现在会完整删除依赖图，不再只删除 match。

## 9. 已知运行边界

以下不是 PR4 的未完成项，但仍属于后续部署/工程质量批次：

1. 当前使用短期 access token，无 refresh token；过期后重新登录。
2. 前端 production bundle 约 1.42 MB，构建成功但有 chunk-size warning；路由 lazy loading 属于后续性能工作。
3. 依赖/secret scan、Python lint/type check 和完整 E2E 应纳入正式 CI。

生产认证状态已改为 Redis 共享；开发/测试内存实现不得用于多实例部署。

## 9.1 工作区保护

重新验收未执行 reset、checkout 或覆盖任务开始前改动。由于当前分支在任务开始前已经混有 PR3、Phase 4 与大量 staged/unstaged/untracked 用户资产，本轮没有强行创建包含这些资产的“PR4 独立提交”；修复和测试结果保留在当前工作区并由本报告逐项追踪。

## 10. 给 Cursor 的后续执行规则

如果让 Cursor 继续 PR5，应先阅读本报告及 `CURSOR_EXECUTION_BACKLOG.md` 第 9 节，并遵守：

1. 不回退 PR3 状态机、快照、授权或 PostgreSQL 并发不变量；
2. 不重新引入客户端可信 employer/candidate ID；
3. 新路由必须加入匿名、错误角色、跨 owner 和合法 owner 测试；
4. 新上传入口必须复用 `safe_upload.py`；
5. 新删除关联必须加入 `privacy.py` 和删除图测试；
6. 多实例配额、限流、撤销和 WebSocket 认证不得依赖进程内状态；
7. PostgreSQL 测试使用独立数据库或串行运行；
8. 不关闭 lint/security 规则制造通过结果。

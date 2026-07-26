# PR5.5 产品与代码收敛：只读差距审计

> 历史审计快照：缺口已按
> `PR5_5_IMPLEMENTATION_AND_VERIFICATION_REPORT.md` 实施；本文件保留用于追溯，
> 其中“当前尚未完成”等表述不代表最新状态。

> 审计日期：2026-07-25  
> 审计范围：`CURSOR_EXECUTION_BACKLOG.md` §10、`CURSOR_REMEDIATION_PLAN.md` §7.4、当前后端/前端实现。  
> 本文件只记录现状与实施边界；本轮没有修改业务代码、数据库或现有用户改动。

## 1. 结论

PR5.5 当前尚未完成。前几批次已经建立了状态机、申请快照、部分统一授权 helper、原子配额和前端状态常量，但它们仍与旧路径并存：

- `backend/app/main.py` 仍承载大量路由和领域判断；
- 授权同时存在 `security.py`、`application_authz.py` 和路由内联判断；
- Application 状态在后端已有状态机，但前端页面仍复制部分状态分支；
- HTTP 错误仍混用字符串和对象，前端多处直接读取或匹配 `detail` 文本；
- `check_quota` / `record_usage` 与新预占路径并存，虽无当前调用方，尚未形成正式删除证据；
- `db_schema.ensure_schema()`、`Base.metadata.create_all()` 与正式 migration 并存；
- 市场数据里的 `Company` 不能承担企业客户、席位和组织计费语义；
- 当前还没有候选人与招聘方两条完整 E2E 链路。

因此 PR5.5 应采用“先锁定契约和测试，再逐域收拢”的方式实施，不能直接批量移动文件或删除兼容代码。

## 2. 两条 canonical journey

### 2.1 候选人旅程

```text
注册/登录
  → 上传并解析简历
  → 履历证据体检 / 忠实建议
  → 补充证据或回答追问
  → 人工预览并采纳忠实补丁
  → 投递并固定 application resume snapshot
  → 查看待澄清 Claim
  → 针对稳定 claim_id 回复
  → 招聘方复核或关闭
  → 接受面试邀请
```

权威边界：

- 简历 owner：authorization service；
- suggestion 可采纳性及证据引用：suggestion/writeback service；
- 忠实度：fidelity service；
- 投递快照：application service；
- Application/Claim 状态：application state machine；
- 额度：billing/metering service。

### 2.2 招聘方旅程

```text
管理员建立企业与席位
  → 招聘方登录
  → 发布岗位
  → 查看与本岗位存在合法申请的候选人
  → 读取投递时简历快照
  → 发起履历可信度审计
  → 创建待澄清 Claim
  → 查看候选人说明
  → 人工复核 / 关闭澄清
  → 发出面试邀请
```

权威边界：

- 企业成员及席位：organization authorization；
- 岗位 ownership：authorization service；
- 申请简历可见性：application authorization；
- 审计使用投递快照，不读取候选人当前可编辑简历；
- 审计共享额度：organization billing service；
- 最终招聘决定：人工，不由可信度状态或模型自动决定。

## 3. 单一事实来源差距

| 领域 | 当前已有 | 当前重复/旁路 | PR5.5 目标 |
|---|---|---|---|
| 身份与对象授权 | `security.py`、`application_authz.py` | `main.py`、`application_routes.py`、`invitation_routes.py`、`analytics_routes.py` 中仍有大量 role/owner 内联判断 | 领域授权函数集中；路由只传入 actor 与 resource id |
| Application 状态 | `application_state.py`、`application_status.py` | 页面和部分路由仍直接比较/拼装状态 | 所有写迁移只走状态机；前端只消费服务端 capability/action |
| Claim 状态 | `claim_threads.py` 与 application JSON | Claim 尚非正式稳定数据模型，页面仍对 open Claim 自行筛选 | PR5.5 先统一服务接口和术语；正式 Claim 表放入 AI 数据模型批次 |
| 投递快照 | JobApplication snapshot/version 相关字段 | 仍需证明每个审计/邀请读取入口都不会回退到工作简历 | 提供统一 `get_application_resume_snapshot()`，回退路径登记并测试 |
| 忠实写回 | `evidence_followup.py`、`fidelity_proof.py`、suggestion store | 路由仍编排较多 proof/patch 规则；当前启发式存在中文专名漏检 | 收拢为 writeback service；PR5.1 先修复检测器和 proof 密钥 |
| 配额/计费 | `reserve_quota()` / `finalize_quota()` | `check_quota()` / `record_usage()`、固定 USD 调用估算、按用户计审计 | PR5.1 建立候选人/企业 entitlement、reservation、provider cost 三账本后删除旧入口 |
| 企业概念 | `companies` 用于市场画像和数据分析 | 无组织、成员、席位模型 | 新建 `organizations` / `organization_memberships`；禁止复用 `companies` |
| 错误契约 | FastAPI 默认 `detail` | 字符串/对象混用，前端还用 `includes()` 猜“已邀请”等业务状态 | 统一 `{error:{code,message,fields,request_id}}`，前端按 code 分支 |
| Schema | SQLAlchemy metadata、`ensure_schema()`、PR5 SQL migration | 三套 schema 权威来源并存 | migration 为唯一生产权威；动态 DDL 只保留明确过渡清单 |

## 4. 术语表

| 内部英文 | 推荐中文 | 明确禁止的误导表达 |
|---|---|---|
| Claim | 履历主张 / 待核验事实 | 谎言、造假事实 |
| Evidence | 证据材料 | 模型猜测、语言风格信号 |
| needs_clarification | 待补充说明 | 可疑、疑似造假 |
| clarified | 已提交说明 / 候选人已说明，待复核 | 已证实、已验证真实 |
| clarification_closed | 澄清已关闭 | 已确认虚假 |
| supported | 有证据支持 | 绝对真实 |
| contradicted | 与当前可靠证据存在实质冲突 | 已判定说谎 |
| insufficient_evidence | 证据不足 | 虚假 |
| unverifiable | 暂不可核验 | 不可信 |
| disputed | 存在争议，待人工处理 | 申诉失败 |
| credibility audit | 履历可信度审计 | 测谎、真假检测 |
| faithful rewrite | 忠实重写 | AI 美化、自动包装 |
| potential delta | 可提升空间模拟 | 录用概率、录用保证 |
| TargetRoleProfile | 目标岗位能力画像 | 大公司偏好画像、成功人士画像 |

`frontend/src/constants/applicationStatus.js` 已正确把 `clarified` 展示为“已提交说明”或“候选人已说明，待复核”，应作为状态文案基线。

## 5. 统一 API 契约草案

### 5.1 成功响应

已有接口可在兼容期继续返回现有 payload；所有 PR5.1/PR5.5 新接口统一：

```json
{
  "data": {},
  "meta": {
    "request_id": "uuid",
    "server_time": "2026-07-25T12:00:00+08:00"
  }
}
```

列表响应：

```json
{
  "data": [],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "next_cursor": null
  }
}
```

### 5.2 错误响应

```json
{
  "error": {
    "code": "billing.quota_exceeded",
    "message": "本周期额度已用尽",
    "fields": {},
    "request_id": "uuid"
  }
}
```

规则：

- `code` 稳定、可供前端分支，`message` 可调整和本地化；
- 401/403/404/409/422/429/502 保留正确 HTTP 语义；
- 不再用 402 表示内部免费额度耗尽，推荐 429；真实支付失败才使用支付域错误；
- 幂等重放不应默认作为 409 错误：若原调用成功，返回原结果或稳定的进行中状态；
- 前端不得再用 `String(detail).includes(...)` 判断“已邀请”等状态；
- 兼容期由 axios interceptor 把旧 `detail` 转成统一客户端错误对象，页面不直接解析旧 envelope。

## 6. 兼容路径清单与处置

### A. 可在测试证明零调用后删除

| 路径 | 当前证据 | 删除前门禁 |
|---|---|---|
| `usage_metering.check_quota()` | 仓库搜索未发现调用方 | 新 billing 路径全量回归；禁止插件式动态 import 后再删 |
| `usage_metering.record_usage()` | 仓库搜索未发现调用方 | provider cost event 与 entitlement event 覆盖所有模型调用后再删 |
| `COST_ESTIMATES` 固定 USD/调用 | 不代表真实 token 成本 | provider usage 采集、价格版本和管理员权限测试完成 |

### B. 必须迁移调用方后删除

| 路径 | 调用方/风险 | 移除条件 | 截止批次 |
|---|---|---|---|
| 路由内联 `resume.user_id` / `job.employer_id` 判断 | `main.py`、application/invitation/analytics routes | 等价授权矩阵测试通过且调用改为 authz service | PR5.5 |
| 页面直接读取 `err.response.data.detail` | 多个候选人/招聘方页面与组件 | interceptor + typed client error 覆盖所有触及页面 | PR5.5，余量 PR7 |
| 页面直接实现 Application 状态动作限制 | `AppliedJobs.jsx`、`Applications.jsx` | 后端返回 `allowed_actions`，前端只负责展示 | PR5.5 |
| 直接使用工作简历的申请相关回退 | 审计、邀请及列表需逐入口确认 | snapshot 缺失时明确迁移/错误，不静默换源 | PR5.5 |
| `db_schema.ensure_schema()` 中 PR5 表 DDL | 启动时执行 | 正式 migration 已进入唯一启动流程并完成存量验证 | PR6/PR7 |
| `Base.metadata.create_all()` 生产启动 | `main.py` lifespan | 部署启动强制 migration，测试 fixture 独立建库 | PR6/PR7 |

### C. 必须保留但澄清含义

| 路径 | 原因 | 处置 |
|---|---|---|
| `companies` / `Company` | 现有市场画像、论坛洞察和分析大量依赖 | 保留为市场实体；新建 `organizations` 表达付费客户与租户 |
| Application `clarified` | 当前状态机和 UI 已采用 | 保留内部 enum，但产品文案始终为“已说明，待复核” |
| SQLite 进程内 quota lock | 本地开发/测试需要 | 标注非生产保证；生产启动拒绝多 worker SQLite |

## 7. “修改痕迹”清理原则

仓库目前存在 `.py~`、`.jsx~`、`.DS_Store`、`frontend.zip` 等疑似编辑器备份或打包痕迹。它们不能仅凭文件名直接删除，因为当前工作区整体属于用户资产。

允许清理的条件：

1. 证明文件没有构建、运行、测试或部署调用方；
2. 对比正式文件，确认不存在只保存在备份中的用户内容；
3. 在单独清理提交中列出文件及可恢复来源；
4. 用户明确授权删除。

代码层面的“错误修改痕迹”不能通过恢复旧文件解决，应以行为测试为准删除重复分支。特别是：

- 不回退已经通过验收的 PR3/PR4 安全控制；
- 不因为新 helper 存在就直接删除路由判断，先补授权矩阵；
- 不删除 `failed` 状态前先决定 provider 调用已发生但业务失败时的成本/额度语义；
- 不复用市场 `Company` 表来节省 migration。

## 8. 推荐模块边界

```text
API routes
├── auth / request schema / response envelope
└── 调用 application service

Domain services
├── authorization
├── applications + state machine
├── claims + clarification
├── resume snapshots
├── suggestions + faithful writeback
├── credibility audit
└── billing + provider costs

Infrastructure
├── repositories / SQLAlchemy
├── model providers
├── Redis events / jobs
└── migrations
```

建议增量拆分，而不是一次移动全部路由：

1. 先为统一错误、authorization 和 billing 建测试；
2. 把 PR5.1 的三个收费入口移入 billing application service；
3. 收拢 Application/Claim 写操作；
4. 收拢忠实写回；
5. 最后把只读列表和展示逻辑迁移。

## 9. PR5.5 需求追踪矩阵

| ID | 用户结果 | 当前证据 | 当前状态 | 验收证据 |
|---|---|---|---|---|
| PR5.5-R01 | 两条 canonical journey 可追踪 | 本文件已定义，尚未映射全部 endpoint | partial | endpoint/page 映射表 + 2 条 E2E |
| PR5.5-R02 | 授权单一事实来源 | helper 与内联判断并存 | fail | 角色/租户矩阵 + 零重复写规则审计 |
| PR5.5-R03 | 状态只由领域状态机迁移 | 后端已有状态机，前端仍复制动作规则 | partial | 状态单测 + API 集成 + UI E2E |
| PR5.5-R04 | 投递快照不与工作简历混用 | PR3 已有快照，但需逐入口证明 | partial | 快照不可变与审计来源测试 |
| PR5.5-R05 | 术语前后端一致 | application 状态文案已有基线 | partial | 词汇扫描 + UI 冒烟 |
| PR5.5-R06 | 统一状态/错误/分页/幂等契约 | 仍混用自由文本 `detail` | fail | contract tests + frontend error tests |
| PR5.5-R07 | 重复计量路径删除 | 两个旧函数零调用但仍存在 | fail | 调用方清单 + 删除 diff + 回归 |
| PR5.5-R08 | 兼容路径有截止批次 | 本文件首次登记 | partial | 实现报告逐条关闭 |
| PR5.5-R09 | 候选人 E2E | 尚无完整自动化链 | fail | 上传→写回→投递→Claim 回复 |
| PR5.5-R10 | 招聘方 E2E | 尚无完整自动化链 | fail | 岗位→申请→审计→澄清→邀请 |
| PR5.5-R11 | lint 不恶化且债务可追踪 | 当前全局 lint 已绿，但需复跑确认 | unverified | scoped/global lint 输出 |
| PR5.5-R12 | 模块边界与删除记录 | 本文件给出目标，尚未实施 | partial | 完成报告与最终依赖扫描 |

## 10. 实施顺序

PR5.5 必须在 PR5.1 收费与忠实度修复稳定后实施：

1. 固化统一 error code、application action、billing feature enum；
2. 写旧实现必然失败的 contract tests；
3. 建 authorization/application/billing application service；
4. 迁移三个昂贵 AI 入口和两条 canonical journey；
5. 前端引入 feature API 与统一错误解析；
6. 删除已证明零调用的旧计量入口和重复状态分支；
7. 运行完整 SQLite/PostgreSQL、前端测试、lint、build；
8. 执行两条浏览器 E2E 并留证；
9. 更新兼容路径清单，未关闭项明确进入 PR7/PR8。

在上述矩阵全部通过前，不应把 PR5.5 标记为完成，也不应宣称当前代码结构已是稳定成品。

# PR11 Implementation and Verification Report

> 文档版本：2026-07-29  
> 范围：Career Passport 与 Evidence Vault Map（含缺口补完）  
> 最终判定：**完成（核心产品 + 病毒扫描/对象存储签名下载 + 写接口幂等 + ResumeVersion PG 门禁 + HTTP/浏览器 E2E）**

## 1. 目标与不包含范围

本批次把 Resume 附属 Claim 扩展为候选人的长期职业记录，并交付服务端授权的四视图记忆网络、Evidence 生命周期和不可变 ResumeVersion。

不包含 PR12 的 AI 追问、结构化 interview session/question/answer/observation；Claim chat 仍为手动记录外壳。

## 2. 需求追踪矩阵

| 需求 | 实现 | 测试 | 状态 |
|---|---|---|---|
| 长期 Career Experience | `career_experiences` + API/UI | owner/运行时 | pass |
| 扩展稳定 Claim | 原表 ALTER + owner 回填 + orphan report | UUID 稳定 | pass |
| Evidence Artifact/关系 | artifact + 扩展 `claim_evidence` | 撤回/跨租户 | pass |
| ResumeVersion 不可变 | version + claim link snapshot | 修改后快照不变 | pass |
| 四视图 Map | timeline/capability/evidence/job | 服务端过滤/分页/job requirement | pass |
| Claim 历史/确认/撤回/合并/拆分 | API + append-only event | merge/split/supersession | pass |
| Evidence 上传安全 | MIME/魔数 + EICAR + ClamAV fail-closed + 私有对象键 | 单测 + Compose HTTP | pass |
| 短时签名下载 URL | app HMAC token（local）/ S3 presign（可选） | 往返下载 + 跨租户 404 | pass |
| 所有写 API 幂等 | `api_idempotency_keys` + `Idempotency-Key` | replay/conflict | pass |
| ResumeVersion PG 并发门禁 | `pg_advisory_xact_lock` + unique + 409 | 8 路真并发 + IntegrityError 映射 | pass |
| 浏览器 / HTTP E2E | Playwright + accept script | UI + 文件上传 + 签名下载 | pass |

## 3. 本轮缺口补完文件

- `backend/app/virus_scan.py`：EICAR 常开；生产 ClamAV 默认 fail-closed
- `backend/app/object_storage.py`：local / S3|MinIO adapter + 签名下载
- `backend/app/api_idempotency.py`：统一写接口 replay ledger（`set_response` 与业务同一事务提交）
- `backend/app/career_vault.py`：ResumeVersion advisory lock + IntegrityError → conflict
- `backend/app/career_vault_routes.py`：全部写 API 接入幂等；文件内容哈希参与指纹；complete-upload 扫毒落库；download-url/download
- `backend/scripts/migrations/20260729_pr11_idempotency_storage_*` + Alembic `pr11_idempotency`
- `frontend/.../CareerPassport.jsx`、`EvidenceVault.jsx`：`Idempotency-Key` 稳定复用；可由浏览器直接消费的短时下载入口
- `backend/tests/test_pr11_gaps.py`、`frontend/e2e/pr11-passport-vault.spec.js`
- `.env.example`、`docker-compose.yml`：对象存储 / 病毒扫描配置项

## 4. 数据模型与迁移

既有 PR11 表外，新增：

- `api_idempotency_keys`（user_id + scope + key 唯一）

Alembic head：`pr11_idempotency`（ledger `20260729_pr11_idempotency_storage`）。

有用户数据时 PR11 主体 downgrade 仍按设计拒绝。

## 5. 验证结果（2026-07-29）

- 全量后端 pytest：通过（含既有 skip）
- PR11 PostgreSQL 真并发：同一 Resume 8 路并发生成版本号 1–8，无重复/丢失
- 前端 unit tests：22 pass
- `npm run lint` / `npm run build`：通过
- `make migrate` → `alembic=pr11_idempotency ledger=12`
- HTTP runtime：`accept_pr10_pr11_runtime.py` 全部 PASS（含幂等 replay）
- Playwright：`e2e/pr11-passport-vault.spec.js` 1 passed（Career Passport + 文件 Evidence 上传 + 无 Bearer 签名下载）
- Compose HTTP：普通 TXT 经 ClamAV 通过；EICAR 被 422 拒绝；短期签名 URL 无 Bearer 下载内容一致
- 运行入口：`http://127.0.0.1:8081`（`APP_PORT=8081`，因 8080 被占用）

## 6. 运维说明

- `OBJECT_STORAGE_BACKEND=local|s3|minio`
- `VIRUS_SCAN_ENABLED=true`（默认）；Compose 使用官方多架构 ClamAV 1.4.5 镜像
- `EVIDENCE_DOWNLOAD_SIGNING_KEY` 优先，否则回退 `SECRET_KEY`
- ClamAV 未配置、不可用或返回异常时默认 fail-closed（`VIRUS_SCAN_FAIL_MODE=closed`），上传返回 503

## 7. 残留风险（非阻断）

1. S3/MinIO adapter 及依赖已装入镜像，但尚未针对真实云 bucket 做集成验收；当前已验收 local 私有卷路径
2. 大图移动端视觉截图未单独归档（Playwright 已覆盖主路径）
3. PR12 AI chat 未开始，符合范围

## 8. 用户资产保护

未 reset、checkout、覆盖或批量格式化工作区无关改动。

## 9. 最终判定

**完成**

PR11 产品骨架与原先标明的四处缺口均已落地并通过自动化/HTTP/浏览器验收，可作为 PR12 基线。

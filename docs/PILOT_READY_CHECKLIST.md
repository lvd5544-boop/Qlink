# QLink Pilot-Ready Checklist / 试用就绪清单

This checklist is the release gate for inviting real candidate testers. It does not claim legal or production certification.

本清单用于判断是否可以邀请真实求职者参加小规模试用，不代表法律合规认证或正式生产认证。

## 1. Product boundary / 产品边界

- QLink does not automatically submit job applications.
- Any generated or inferred candidate information remains unconfirmed until the candidate explicitly approves it.
- Pilot participation, aggregated metrics, and model-improvement permission are separate choices.
- Model-improvement permission is off by default.
- Withdrawing from the pilot stops future pilot research use. Account deletion is a separate, explicit, irreversible action.

- QLink 不自动提交求职申请。
- 生成或推测的候选人信息在用户明确确认前，不得成为个人事实。
- 试用参与、去标识汇总指标和模型改进授权相互独立。
- 模型改进授权默认关闭。
- 退出 pilot 停止后续试用研究使用；删除账号是独立、明确且不可撤销的操作。

## 2. Release gate / 发布门槛

Run from the repository root:

```bash
make test
docker compose config --quiet
docker compose run --rm migration
cd frontend && npx playwright test e2e/pilot-ready.spec.js
make production-go-live-preflight PRODUCTION_ENV_FILE=.env.production
```

Before sharing the registration URL, replace `LEGAL_ENTITY_NAME`, `SUPPORT_EMAIL`, and `PRIVACY_CONTACT_EMAIL` with the accountable operator and monitored inboxes. Open `/privacy` and `/terms` in the deployed site, verify those runtime details, and obtain any required jurisdiction-specific legal review. Registration must remain blocked until both notices are acknowledged; the accepted notice versions are stored with the account and deleted with it.

在分享注册链接之前，必须把 `LEGAL_ENTITY_NAME`、`SUPPORT_EMAIL` 和 `PRIVACY_CONTACT_EMAIL` 替换为真实负责主体与有人值守的邮箱。在部署站点打开 `/privacy` 和 `/terms`，核对运行时信息，并按适用地区完成必要法律审查。用户未分别确认两份说明时不得创建账号；接受版本随账号保存，删除账号时一并删除。

Before the first real tester and after any storage change, run one restore rehearsal using synthetic data. Verify that a database marker, an uploaded file, and an Evidence Vault file all survive the backup/restore round trip. Follow [BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md); never use a real-user environment for the rehearsal.

首位真实测试用户进入前，以及每次存储配置变更后，都要使用合成数据完成一次恢复演练，确认数据库标记、普通上传文件和 Evidence Vault 文件均能经过备份/恢复往返。操作见 [BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md)，禁止在真实用户环境中演练。

For a deployed pilot environment, also complete the candidate browser flow in `MANUAL_ACCEPTANCE_GUIDE.md`:

1. Open the public privacy notice and terms, verify operator contacts, then register a new candidate account after explicitly acknowledging both.
2. Open **Pilot & Feedback**, review consent, and join with model improvement disabled.
3. Choose or import a target role.
4. Upload a test resume with no real sensitive data.
5. Verify extracted facts before accepting any change.
6. Review the diagnostic and tailored resume flow.
7. Record an application outcome manually; verify there is no automatic external submission.
8. Submit pilot feedback once, then retry the request and verify no duplicate row is created.
9. Withdraw from the pilot and verify feedback submission is blocked.
10. With a disposable test account, verify account deletion removes the account and associated private graph.

Do not invite users if migration, readiness, core browser flow, ownership tests, or account deletion fails.

Do not set the go-live confirmation flags merely to make the command green. Keep private evidence for the off-host backup target, restore rehearsal identifier and result, alert-delivery test, and legal/processor/retention review. Missing evidence means the gate has not passed even if an environment file says `true`.

不要为了让命令通过而直接修改确认标志。异地备份位置、恢复演练编号与结果、告警送达测试、法律/处理方/保留周期复核都必须在私有负责人记录中有证据；没有证据就不算通过。

## 3. Cohort rollout / 用户分批

- Wave 0: maintainer plus synthetic accounts.
- Wave 1: 3–5 closely supported users.
- Wave 2: expand beyond 5 only after all Wave 1 blockers are triaged.
- Keep one support channel and a response owner for every wave.
- Pause invitations for data loss, cross-account access, misleading fact confirmation, unusable core flow, or any external action without preview and approval.

- 第 0 波：维护者与合成测试账号。
- 第 1 波：3–5 名可近距离支持的用户。
- 第 2 波：只有第 1 波阻塞问题完成分类和处理后，才扩大到 5 人以上。
- 每一波必须有一个统一反馈渠道和明确负责人。
- 如发生数据丢失、越权访问、错误确认候选人事实、核心流程不可用，或未经预览确认的外部动作，立即暂停邀请。

## 4. Data handling / 数据处理

- Never copy real resumes, uploads, database exports, feedback exports, tokens, or `.env` files into Git or issues.
- Pilot feedback is linked to a random participant code instead of an email in the pilot tables.
- Free-text feedback warns users not to enter passwords, identity numbers, or other sensitive information.
- Access to raw feedback should be restricted to the pilot operator; publish only aggregated findings.
- Before later PyTorch training, define a separate consented, de-identified training dataset and a deletion/withdrawal process. Pilot participation alone is not training consent.

## 5. Pilot owner log / 试用负责人记录

Record these outside the public repository:

- deployment version and migration head;
- tester participant code, not email;
- session date and journey completed;
- blocker severity and resolution owner;
- consent status at the time of data use;
- withdrawal or deletion requests and completion time.

Use [C6_PILOT_PROTOCOL.md](./C6_PILOT_PROTOCOL.md) for interview questions, measures, and Go / Iterate / Stop decisions.

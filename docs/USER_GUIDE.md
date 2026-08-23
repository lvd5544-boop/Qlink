# QLink User Guide / 用户使用手册

This guide describes the current pilot Demo. Labels may evolve as the product moves toward production.<br>
本手册对应当前试点 Demo，产品进入生产阶段时，页面名称和权限可能继续调整。

Before registration, open **Privacy / 隐私说明** and **Terms / 服务条款** from the account page. The deployment operator and monitored contact addresses must be visible. Account creation requires acknowledging each document separately; joining the pilot and allowing model improvement remain later, independent choices.<br>
注册前，请从账号页面打开 **Privacy / 隐私说明** 和 **Terms / 服务条款**，确认可见真实运营方与联系邮箱。创建账号需要分别确认两份说明；参加试用和允许模型改进仍是后续独立选择。

## 中文

### 1. 启动并注册

1. 按仓库 README 启动服务并打开 `http://localhost:8080`。
2. 点击“立即注册”创建求职者账号。
3. 使用注册邮箱和密码登录。

公开注册只创建求职者账号。招聘方账号需要企业邀请码，管理员账号需要由部署方安全创建。

### 2. 建立真实履历

1. 进入“上传简历”。
2. 上传 PDF、Word 或 TXT 简历。
3. 在“我的简历”检查解析结果。
4. 修正姓名、技能、经历和时间线等字段。
5. 对 AI 建议逐条确认；没有证据的内容不要写入正式简历。

上传文件可能包含高度敏感的个人信息。公开演示时请使用虚构的测试资料，不要上传真实身份证件、住址或未授权的第三方信息。

### 3. 选择目标岗位

用户可以在“搜索全部岗位”或“岗位推荐”中选择岗位，也可以在求职顾问流程中导入自己的目标 JD。私有 JD 仅应对创建者和获得明确授权的服务开放。

### 4. 阅读机会准备卡

准备卡把岗位要求分为：

- 现在可用：已有明确证据；
- 需要说清：可能具备，但需要更具体地表达；
- 发展行动：需要补充作品、学习或实践；
- 现实约束：地点、时间、资格等客观限制；
- 待验证假设：系统无法根据现有材料确认。

准备度用于安排下一步行动，不等于录用概率。

### 5. 优化简历和准备申请

1. 选择目标岗位和基础简历。
2. 阅读针对性建议及其依据。
3. 确认所有新增表述都来自真实经历。
4. 保存新的简历版本，不覆盖未经确认的原始材料。
5. 在提交任何外部申请前预览完整表单和附件。

当前范围不包括未经用户确认的批量自动投递。

### 6. 结构化面试

1. 选择目标岗位并开始面试。
2. 回答时说明背景、行动、结果和个人贡献。
3. 面试结束后检查系统生成的观察结果。
4. 只有用户确认的观察结果才能进入长期经历记录或向招聘方分享。

### 7. 跟踪申请

在“投递记录”查看申请状态、招聘方澄清请求和面试邀请。状态变化应来自用户操作、招聘方操作或经过授权的集成，不应由模型自行推断。

### 8. 招聘方流程

1. 使用邀请码开通企业账号。
2. 发布或导入岗位 JD。
3. 确认岗位要求，尤其是硬性约束。
4. 仅查看已授权进入相应流程的候选人。
5. 人工复核匹配、批筛和履历一致性信息。
6. 请求澄清、发起面试邀请或更新申请状态。

系统输出是辅助材料，不应作为自动拒绝或歧视性筛选的唯一依据。

### 9. 账号安全与找回

登录页的“忘记密码”会向已注册邮箱发送短时、一次性重置链接；无论邮箱是否存在，页面都显示相同结果。登录后可在“账号安全”修改密码，成功后当前设备与其他设备都会退出。若部署方尚未配置 SMTP，重置邮件不会发送，请联系试用负责人。

## English

### 1. Start and register

Start the stack using the repository README, open `http://localhost:8080`, and create a candidate account from the registration page. Public registration creates candidate accounts only. Employer accounts require an invitation, and administrators must be provisioned securely by the operator.

### 2. Build a factual profile

Upload a PDF, Word, or TXT resume, review the parsed profile under “My Resumes,” correct the extracted fields, and accept AI suggestions only when they are supported by real experience. Use synthetic data in public demos and never upload identity documents or unauthorized third-party information.

### 3. Choose a target role

Select a role from browse or recommendation pages, or import a private target JD through the advisor workflow. A private JD should remain available only to its owner and explicitly authorized services.

### 4. Review readiness

The opportunity card separates demonstrated evidence, items that need clearer explanation, development actions, real-world constraints, and assumptions that still require verification. Readiness prioritizes preparation; it is not a prediction of hiring probability.

### 5. Tailor and prepare

Choose a target role and source resume, review each suggestion and its evidence, confirm every factual claim, save a separate version, and preview the complete form and attachments before any external submission. Unconfirmed batch auto-submission is not part of the current scope.

### 6. Practice an interview

Run a structured interview for the target role, explain context, actions, results, and personal contribution, then review generated observations. Only candidate-confirmed observations may enter durable career records or be shared with an employer.

### 7. Track applications

Use Application History to follow status changes, clarification requests, and invitations. Status must come from a user action, an employer action, or an authorized integration—not an unsupported model inference.

### 8. Employer workflow

Join by invitation, publish or import a JD, confirm requirements and hard constraints, review only authorized candidates, human-review system output, then request clarification, invite, or update application state. AI output is assistance and must not become the sole basis for automatic rejection or discriminatory screening.

### 9. Account security and recovery

Use “Forgot password” on the login page to request a short-lived, single-use reset link. The page shows the same result whether or not an account exists. Signed-in users can change their password under Account Security; a successful change signs out every device. Recovery email is unavailable until the operator configures SMTP.

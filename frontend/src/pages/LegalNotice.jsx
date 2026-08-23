import { useEffect, useState } from 'react';
import { Alert, Card, Divider, Space, Spin, Typography } from 'antd';
import { Link } from 'react-router-dom';
import api from '../api';

const { Title, Paragraph, Text } = Typography;

const PRIVACY_SECTIONS = [
  ['我们处理什么 / What we process', '账号邮箱，以及你主动提交的简历、目标岗位、证据、面试练习、申请状态、试用授权和反馈。系统安全日志使用请求标识；请勿在反馈中填写身份证号、密码等敏感信息。 / Account email and the resumes, target roles, evidence, interview practice, application status, pilot choices, and feedback you submit. Security logs use request identifiers; do not place passwords or government identifiers in feedback.'],
  ['为什么处理 / Why we process it', '用于提供求职准备工作流、保护账号、诊断故障和执行你选择的试用研究。模型改进是独立授权，默认关闭；退出试用会停止未来的试用研究使用。 / To provide the job-preparation workflow, secure accounts, diagnose failures, and conduct only the pilot research you select. Model improvement is separate and off by default; withdrawal stops future pilot research use.'],
  ['你的控制权 / Your controls', 'AI 推断不会自动成为你的事实。你可以查看、确认或拒绝建议，退出试用，并通过“账号安全”永久删除账号及关联私有数据。 / AI inferences do not automatically become your facts. You can review, accept, or reject suggestions, leave the pilot, and permanently delete your account and associated private data from Account Security.'],
  ['共享与跨境 / Processors and transfers', '部署方可能使用托管、数据库、邮件、病毒扫描和模型供应商。实际供应商、数据地区、保存期限及法律依据必须由部署方在邀请用户前另行披露。 / The operator may use hosting, database, email, malware-scanning, and model providers. The operator must disclose the actual providers, data regions, retention periods, and legal basis before inviting users.'],
];

const TERMS_SECTIONS = [
  ['产品范围 / Product scope', 'QLink 是有限试用的求职准备工具，不是招聘决定系统、职业结果保证或自动投递服务。外部提交、消息和其他高影响操作需要用户可见预览与明确批准。 / QLink is a limited-pilot job-preparation tool, not a hiring-decision system, employment guarantee, or autonomous application service. External submissions, messages, and other high-impact actions require a visible preview and explicit approval.'],
  ['用户责任 / User responsibilities', '仅上传你有权处理的内容；核对生成材料，不得把未经证实的信息作为事实提交；不得绕过访问控制、限流或第三方网站条款。 / Upload only content you are authorized to process; review generated material and do not submit unverified information as fact; do not bypass access controls, rate limits, or third-party terms.'],
  ['试用限制 / Pilot limitations', '服务可能出错或中断。请勿依赖它作出紧急、法律、财务或最终招聘决定。发现数据泄露、越权或误导性确认时应停止使用并联系部署方。 / The service may make mistakes or be unavailable. Do not rely on it for emergency, legal, financial, or final hiring decisions. Stop using it and contact the operator if you detect data loss, unauthorized access, or misleading confirmation.'],
  ['账号与终止 / Account and termination', '你应保护登录凭据。你可以修改密码、退出全部设备或删除账号；部署方也可为安全、滥用或试用结束暂停访问。 / Protect your credentials. You may change your password, sign out all devices, or delete your account; the operator may suspend access for security, abuse, or when the pilot ends.'],
];

export default function LegalNotice({ kind }) {
  const [config, setConfig] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.get('/auth/legal-notice')
      .then((response) => setConfig(response.data))
      .catch(() => setFailed(true));
  }, []);

  const privacy = kind === 'privacy';
  const sections = privacy ? PRIVACY_SECTIONS : TERMS_SECTIONS;
  const version = privacy ? config?.privacy_notice_version : config?.terms_version;

  return (
    <main style={{ maxWidth: 880, margin: '0 auto', padding: '32px 20px 64px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Link to="/register">← 返回注册 / Back to registration</Link>
          <Title level={1} style={{ marginTop: 16 }}>
            {privacy ? '隐私说明 / Privacy Notice' : '服务条款 / Terms of Service'}
          </Title>
          <Text type="secondary">版本 / Version: {version || 'loading'}</Text>
        </div>

        {failed && (
          <Alert
            type="error"
            showIcon
            message="无法加载部署方身份和联系方式；请暂勿注册 / Operator details unavailable; do not register yet"
          />
        )}

        {!config && !failed ? <Spin /> : config && (
          <Alert
            type="info"
            showIcon
            message={`运营方 / Operator: ${config.operator}`}
            description={`支持 / Support: ${config.support_email} · 隐私联系 / Privacy: ${config.privacy_email}`}
          />
        )}

        {sections.map(([title, content]) => (
          <Card key={title}>
            <Title level={3}>{title}</Title>
            <Paragraph style={{ whiteSpace: 'pre-line', marginBottom: 0 }}>{content}</Paragraph>
          </Card>
        ))}

        <Divider />
        <Alert
          type="warning"
          showIcon
          message="有限试用说明 / Limited-pilot notice"
          description="本文是当前试用产品中的版本化用户说明，不代表法律认证。部署方必须在真实用户进入前补充适用地区、保存期限、实际外部处理方和必要的法律审查。 / This is the versioned notice in the current pilot product, not legal certification. Before real users join, the operator must add jurisdiction-specific terms, retention periods, actual processors, and any required legal review."
        />
      </Space>
    </main>
  );
}

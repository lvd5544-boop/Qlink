import { Card, Typography } from 'antd';
import {
  AuditOutlined,
  CheckCircleFilled,
  FileDoneOutlined,
  RocketOutlined,
} from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const FEATURES = [
  { step: '01', icon: <AuditOutlined />, title: '读懂目标岗位', text: '选平台岗位，或粘贴你真正想投的 JD' },
  { step: '02', icon: <CheckCircleFilled />, title: '对照你的真实履历', text: '看懂优势、材料缺口和最优先的改进项' },
  { step: '03', icon: <FileDoneOutlined />, title: '生成当前可投方案', text: '得到针对岗位的简历版本、投递准备与提升行动' },
];

export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="auth-page">
      <div className="auth-brand">
        <div className="auth-brand-kicker"><RocketOutlined /> QLink AI 求职工作流</div>
        <Title level={1}>从岗位要求到可投版本，<br />一条主线完成</Title>
        <Paragraph className="auth-brand-description">
          不再在一堆 AI 工具之间来回切换。QLink 用一个目标岗位串起分析、简历优化、投递与面试准备。
        </Paragraph>
        <div className="auth-brand-features">
          {FEATURES.map((item) => (
            <div key={item.step} className="auth-brand-feature">
              <span className="auth-brand-feature-step">{item.step}</span>
              <span className="auth-brand-feature-icon">{item.icon}</span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.text}</small>
              </span>
            </div>
          ))}
        </div>
        <div className="auth-brand-proof">基于真实履历 · 你对每条 AI 建议保留决定权</div>
      </div>
      <div className="auth-form-panel">
        <Card className="auth-card" variant="borderless">
          <div className="auth-mobile-pitch">
            <span><RocketOutlined /> AI 求职工作流</span>
            <strong>选岗位 → 对照简历 → 生成可投方案</strong>
          </div>
          <div className="auth-logo">
            <div className="auth-logo-mark">Q</div>
            <Title level={3} style={{ margin: 0 }}>
              {title}
            </Title>
            {subtitle && (
              <Paragraph type="secondary" style={{ marginTop: 4 }}>
                {subtitle}
              </Paragraph>
            )}
          </div>
          {children}
        </Card>
      </div>
    </div>
  );
}

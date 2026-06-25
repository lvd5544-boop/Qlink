import { Card, Typography } from 'antd';
import {
  RobotOutlined,
  SearchOutlined,
  TeamOutlined,
} from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const FEATURES = [
  { icon: <RobotOutlined />, text: 'AI 解析简历与岗位，智能结构化' },
  { icon: <SearchOutlined />, text: '基于画像的精准岗位匹配推荐' },
  { icon: <TeamOutlined />, text: '虚拟面试与线上面试邀请一站式管理' },
];

export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="auth-page">
      <div className="auth-brand">
        <Title level={1}>快连 QLink</Title>
        <Paragraph>AI 驱动的智能招聘与求职平台</Paragraph>
        <div className="auth-brand-features">
          {FEATURES.map((item, i) => (
            <div key={i} className="auth-brand-feature">
              {item.icon}
              <span>{item.text}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="auth-form-panel">
        <Card className="auth-card" bordered={false}>
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

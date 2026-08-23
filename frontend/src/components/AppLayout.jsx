import { Layout, Menu, Button, Typography, Space, Tag } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import api from '../api';
import { disableEnglishDemoMode, isEnglishDemoMode } from '../utils/demoMode';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const ROLE_LABEL = {
  candidate: '求职者',
  employer: '招聘方',
};

function findMenuItem(items, pathname) {
  for (const item of items) {
    if (item.key === pathname) return item;
    const nested = item.children && findMenuItem(item.children, pathname);
    if (nested) return nested;
  }
  return null;
}

function parentKeys(items, pathname, parents = []) {
  for (const item of items) {
    if (item.key === pathname) return parents;
    if (item.children) {
      const nested = parentKeys(item.children, pathname, [...parents, item.key]);
      if (nested) return nested;
    }
  }
  return null;
}

export default function AppLayout({ brandTitle, brandSubtitle, menuItems, role, journey }) {
  const navigate = useNavigate();
  const location = useLocation();
  const englishDemo = isEnglishDemoMode();

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout');
    } finally {
      localStorage.clear();
      navigate('/login');
    }
  };

  const currentPage = findMenuItem(menuItems, location.pathname);
  const defaultOpenKeys = parentKeys(menuItems, location.pathname) || [];

  return (
    <Layout className="app-layout">
      <Sider
        className="app-sider"
        collapsible
        breakpoint="lg"
        width={240}
        theme="light"
      >
        <div className="app-sider-logo">
          <div className="app-sider-logo-mark">Q</div>
          <div className="app-sider-logo-text">
            <div className="app-sider-logo-title">{brandTitle}</div>
            <div className="app-sider-logo-sub">{brandSubtitle}</div>
          </div>
        </div>
        <Menu
          className="app-menu"
          theme="light"
          mode="inline"
          selectedKeys={[location.pathname]}
          defaultOpenKeys={defaultOpenKeys}
          items={menuItems}
          onClick={({ key }) => {
            if (String(key).startsWith('/')) navigate(key);
          }}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Text className="app-header-title">
            {currentPage?.label || brandTitle}
          </Text>
          <Space className="app-header-actions">
            {englishDemo && <Tag color="blue">ENGLISH DEMO</Tag>}
            <Text type="secondary" style={{ fontSize: 13 }}>
              <UserOutlined /> {englishDemo
                ? ({ candidate: 'Candidate', employer: 'Employer' }[role] || 'User')
                : (ROLE_LABEL[role] || '用户')}
            </Text>
            {englishDemo && (
              <Button
                type="text"
                onClick={() => {
                  disableEnglishDemoMode();
                  window.location.reload();
                }}
              >
                Exit Demo
              </Button>
            )}
            <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout}>
              {englishDemo ? 'Log out' : '退出'}
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          <div className="app-content-inner">
            {journey?.length > 0 && (
              <div className="candidate-journey" aria-label={englishDemo ? 'Core application flow' : '求职主流程'}>
                <Text type="secondary" className="candidate-journey-label">
                  {englishDemo ? 'Core flow' : '当前主线'}
                </Text>
                <Space wrap size={4}>
                  {journey.map((step, index) => (
                    <Button
                      key={step.path}
                      type={location.pathname === step.path ? 'primary' : 'text'}
                      size="small"
                      onClick={() => navigate(step.path)}
                    >
                      {index + 1}. {step.label}
                    </Button>
                  ))}
                </Space>
              </div>
            )}
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

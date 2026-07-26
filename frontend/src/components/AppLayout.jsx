import { Layout, Menu, Button, Typography, Space } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import api from '../api';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const ROLE_LABEL = {
  candidate: '求职者',
  employer: '招聘方',
};

export default function AppLayout({ brandTitle, brandSubtitle, menuItems, role }) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout');
    } finally {
      localStorage.clear();
      navigate('/login');
    }
  };

  const currentPage = menuItems.find((item) => item.key === location.pathname);

  return (
    <Layout className="app-layout">
      <Sider
        collapsible
        breakpoint="lg"
        width={240}
        style={{ background: '#0f172a' }}
      >
        <div className="app-sider-logo">
          <div className="app-sider-logo-mark">Q</div>
          <div className="app-sider-logo-text">
            <div className="app-sider-logo-title">{brandTitle}</div>
            <div className="app-sider-logo-sub">{brandSubtitle}</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Text className="app-header-title">
            {currentPage?.label || brandTitle}
          </Text>
          <Space>
            <Text type="secondary" style={{ fontSize: 13 }}>
              <UserOutlined /> {ROLE_LABEL[role] || '用户'}
            </Text>
            <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout}>
              退出
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          <div className="app-content-inner">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

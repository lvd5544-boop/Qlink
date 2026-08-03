import { Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useEffect } from 'react';
import AuthLayout from '../components/AuthLayout';
import api from '../api';

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('reason') === 'session_expired') {
      message.warning('登录已过期，请重新登录后继续');
    }
  }, [searchParams]);

  const onFinish = async (values) => {
    try {
      const res = await api.post('/auth/login', values);
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('role', res.data.role);
      localStorage.setItem('user_id', res.data.user_id);
      message.success('登录成功');
      const defaultPath = res.data.role === 'candidate'
        ? '/candidate/dashboard'
        : res.data.role === 'admin'
          ? '/admin/data-sources'
          : '/employer/dashboard';
      const requestedPath = searchParams.get('returnTo');
      const allowedPrefix = res.data.role === 'candidate'
        ? '/candidate/'
        : res.data.role === 'admin'
          ? '/admin/'
          : '/employer/';
      navigate(requestedPath?.startsWith(allowedPrefix) ? requestedPath : defaultPath);
    } catch {
      message.error('登录失败，请检查邮箱和密码');
    }
  };

  return (
    <AuthLayout title="欢迎回来" subtitle="登录您的 QLink 账号">
      <Form onFinish={onFinish} size="large" layout="vertical" style={{ marginTop: 8 }}>
        <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
          <Input prefix={<UserOutlined />} placeholder="邮箱" />
        </Form.Item>
        <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
          <Input.Password prefix={<LockOutlined />} placeholder="密码" />
        </Form.Item>
        <Form.Item style={{ marginBottom: 12 }}>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form.Item>
      </Form>
      <div style={{ textAlign: 'center', color: '#64748b' }}>
        还没有账号？ <Link to="/register">立即注册</Link>
      </div>
    </AuthLayout>
  );
}

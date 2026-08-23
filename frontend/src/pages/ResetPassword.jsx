import { Alert, Button, Form, Input, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import api from '../api';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const onFinish = async ({ password }) => {
    try {
      await api.post('/auth/password-reset/confirm', {
        token,
        new_password: password,
      });
      navigate('/login?reason=password_reset', { replace: true });
    } catch (error) {
      message.error(error.response?.data?.detail || '链接无效或已过期，请重新申请');
    }
  };

  return (
    <AuthLayout title="设置新密码" subtitle="成功后，所有已登录设备都会退出">
      {!token ? (
        <Alert
          type="error"
          showIcon
          message="重置链接不完整"
          action={<Link to="/forgot-password">重新申请</Link>}
        />
      ) : (
        <Form onFinish={onFinish} size="large" layout="vertical">
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 10, message: '至少 10 位，并包含大小写字母和数字' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="新密码" />
          </Form.Item>
          <Form.Item
            name="confirm"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>更新密码</Button>
        </Form>
      )}
    </AuthLayout>
  );
}

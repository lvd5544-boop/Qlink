import { Alert, Button, Card, Form, Input, Typography, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../api';

const { Title, Paragraph } = Typography;

export default function AccountSecurity() {
  const navigate = useNavigate();

  const onFinish = async ({ currentPassword, newPassword }) => {
    try {
      await api.post('/auth/password/change', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      localStorage.clear();
      navigate('/login?reason=password_changed', { replace: true });
    } catch (error) {
      message.error(error.response?.data?.detail || '修改失败，请检查当前密码');
    }
  };

  return (
    <Card style={{ maxWidth: 640 }}>
      <Title level={3}>账号安全</Title>
      <Paragraph type="secondary">修改密码后，当前设备和其他设备上的登录都会立即失效。</Paragraph>
      <Alert type="info" showIcon message="密码至少 10 位，并包含大写字母、小写字母和数字。" />
      <Form onFinish={onFinish} layout="vertical" style={{ marginTop: 20 }}>
        <Form.Item name="currentPassword" label="当前密码" rules={[{ required: true }]}>
          <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="newPassword"
          label="新密码"
          rules={[{ required: true }, { min: 10, message: '至少 10 位' }]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirmPassword"
          label="确认新密码"
          dependencies={['newPassword']}
          rules={[
            { required: true },
            ({ getFieldValue }) => ({
              validator(_, value) {
                return value === getFieldValue('newPassword')
                  ? Promise.resolve()
                  : Promise.reject(new Error('两次密码不一致'));
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit">修改密码并退出所有设备</Button>
      </Form>
    </Card>
  );
}

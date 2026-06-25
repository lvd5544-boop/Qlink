import { Form, Input, Button, message, Radio } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import api from '../api';

export default function Register() {
  const navigate = useNavigate();

  const onFinish = async (values) => {
    try {
      await api.post('/auth/register', values);
      message.success('注册成功，请登录');
      navigate('/login');
    } catch {
      message.error('注册失败，邮箱可能已存在');
    }
  };

  return (
    <AuthLayout title="创建账号" subtitle="加入快连 QLink 智能招聘平台">
      <Form onFinish={onFinish} size="large" layout="vertical" style={{ marginTop: 8 }}>
        <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
          <Input prefix={<UserOutlined />} placeholder="邮箱" />
        </Form.Item>
        <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
          <Input.Password prefix={<LockOutlined />} placeholder="密码" />
        </Form.Item>
        <Form.Item name="role" rules={[{ required: true, message: '请选择角色' }]}>
          <Radio.Group style={{ width: '100%' }}>
            <Radio.Button value="candidate" style={{ width: '50%', textAlign: 'center' }}>
              求职者
            </Radio.Button>
            <Radio.Button value="employer" style={{ width: '50%', textAlign: 'center' }}>
              招聘方
            </Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Form.Item style={{ marginBottom: 12 }}>
          <Button type="primary" htmlType="submit" block>
            注册
          </Button>
        </Form.Item>
      </Form>
      <div style={{ textAlign: 'center', color: '#64748b' }}>
        已有账号？ <Link to="/login">立即登录</Link>
      </div>
    </AuthLayout>
  );
}

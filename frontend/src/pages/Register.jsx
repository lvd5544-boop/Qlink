import { Form, Input, Button, message, Alert, Checkbox } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import AuthLayout from '../components/AuthLayout';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';

export default function Register() {
  const navigate = useNavigate();

  const onFinish = async (values) => {
    try {
      await api.post('/auth/register', values);
      message.success('注册成功，请登录');
      navigate('/login');
    } catch (error) {
      message.error(getApiErrorMessage(error, '注册失败，请检查填写内容'));
    }
  };

  return (
    <AuthLayout title="创建账号" subtitle="加入快连 QLink 智能招聘平台">
      <Form onFinish={onFinish} size="large" layout="vertical" style={{ marginTop: 8 }}>
        <Form.Item name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
          <Input prefix={<UserOutlined />} placeholder="邮箱" />
        </Form.Item>
        <Form.Item
          name="password"
          rules={[
            { required: true, message: '请输入密码' },
            {
              pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{10,}$/,
              message: '至少 10 位，并包含大写字母、小写字母和数字',
            },
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder="密码" />
        </Form.Item>
        <Alert
          type="info"
          showIcon
          title="公开注册将创建求职者账号；招聘方账号需使用企业邀请码开通。"
          style={{ marginBottom: 16 }}
        />
        <Form.Item
          name="privacy_notice_acknowledged"
          valuePropName="checked"
          rules={[{
            validator: (_, checked) => checked
              ? Promise.resolve()
              : Promise.reject(new Error('请先阅读并确认隐私说明')),
          }]}
        >
          <Checkbox>
            我已阅读 <Link to="/privacy" target="_blank">隐私说明 / Privacy Notice</Link>
          </Checkbox>
        </Form.Item>
        <Form.Item
          name="terms_accepted"
          valuePropName="checked"
          rules={[{
            validator: (_, checked) => checked
              ? Promise.resolve()
              : Promise.reject(new Error('请先阅读并同意服务条款')),
          }]}
        >
          <Checkbox>
            我同意 <Link to="/terms" target="_blank">服务条款 / Terms of Service</Link>
          </Checkbox>
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

import { Button, Form, Input, Alert } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import AuthLayout from '../components/AuthLayout';
import api from '../api';

export default function ForgotPassword() {
  const [submitted, setSubmitted] = useState(false);

  const onFinish = async (values) => {
    try {
      await api.post('/auth/password-reset/request', values);
    } finally {
      // The same result is shown for every account to prevent email enumeration.
      setSubmitted(true);
    }
  };

  return (
    <AuthLayout title="找回密码" subtitle="我们会向已注册邮箱发送一次性链接">
      {submitted ? (
        <Alert
          type="success"
          showIcon
          message="如果该邮箱已注册，重置邮件会很快送达"
          description="请检查收件箱与垃圾邮件。链接仅可使用一次，并会在短时间后失效。"
        />
      ) : (
        <Form onFinish={onFinish} size="large" layout="vertical">
          <Form.Item
            name="email"
            rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}
          >
            <Input prefix={<MailOutlined />} placeholder="注册邮箱" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>发送重置链接</Button>
        </Form>
      )}
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/login">返回登录</Link>
      </div>
    </AuthLayout>
  );
}

import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  List,
  Modal,
  Rate,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import { DeleteOutlined, ExperimentOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../../api';
import { createIdempotencyTracker } from '../../utils/idempotency';

const { Paragraph, Text, Title } = Typography;

const PILOT_STEPS = [
  '选择一个真实目标岗位 / Choose one real target role',
  '上传简历并检查系统识别结果 / Upload a resume and verify extracted facts',
  '查看诊断、建议与针对性版本 / Review diagnostics and a tailored version',
  '记录投递结果并提交反馈 / Record the outcome and share feedback',
];

export default function PilotHub() {
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [consentSaving, setConsentSaving] = useState(false);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePhrase, setDeletePhrase] = useState('');
  const [consentForm] = Form.useForm();
  const [feedbackForm] = Form.useForm();
  const consentIdempotency = useRef(createIdempotencyTracker('pilot-consent'));
  const withdrawIdempotency = useRef(createIdempotencyTracker('pilot-withdraw'));
  const feedbackIdempotency = useRef(createIdempotencyTracker('pilot-feedback'));

  useEffect(() => {
    let active = true;
    api.get('/pilot/me')
      .then((response) => {
        if (!active) return;
        setState(response.data);
        consentForm.setFieldsValue({
          product_research: true,
          aggregate_metrics: response.data.aggregate_metrics || false,
          model_improvement: response.data.model_improvement || false,
        });
      })
      .catch(() => {
        if (active) message.error('暂时无法加载试用设置，请稍后重试');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [consentForm]);

  const saveConsent = async (values) => {
    setConsentSaving(true);
    const payload = {
      product_research: true,
      aggregate_metrics: Boolean(values.aggregate_metrics),
      model_improvement: Boolean(values.model_improvement),
    };
    const key = consentIdempotency.current.keyFor(payload);
    try {
      const response = await api.post('/pilot/consent', payload, {
        headers: { 'Idempotency-Key': key },
      });
      consentIdempotency.current.complete(key);
      setState(response.data);
      message.success('试用授权已保存，你可以随时修改或退出');
    } catch {
      message.error('保存失败，请稍后重试');
    } finally {
      setConsentSaving(false);
    }
  };

  const withdraw = async () => {
    const payload = { action: 'withdraw' };
    const key = withdrawIdempotency.current.keyFor(payload);
    setConsentSaving(true);
    try {
      const response = await api.post('/pilot/withdraw', null, {
        headers: { 'Idempotency-Key': key },
      });
      withdrawIdempotency.current.complete(key);
      setState(response.data);
      message.success('你已退出 pilot；这不会删除你的账号');
    } catch {
      message.error('退出失败，请稍后重试');
    } finally {
      setConsentSaving(false);
    }
  };

  const submitFeedback = async (values) => {
    const payload = { ...values, context: window.location.pathname };
    const key = feedbackIdempotency.current.keyFor(payload);
    setFeedbackSaving(true);
    try {
      await api.post('/pilot/feedback', payload, {
        headers: { 'Idempotency-Key': key },
      });
      feedbackIdempotency.current.complete(key);
      feedbackForm.resetFields();
      message.success('反馈已收到，谢谢你帮助我们改进');
    } catch (error) {
      message.error(error.apiError?.message || '提交失败，请稍后重试');
    } finally {
      setFeedbackSaving(false);
    }
  };

  const deleteAccount = async () => {
    setDeleteSaving(true);
    try {
      await api.delete('/auth/account');
      localStorage.clear();
      window.location.assign('/login?reason=account_deleted');
    } catch {
      message.error('账号删除失败，请稍后重试或联系项目维护者');
      setDeleteSaving(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card>
          <Space align="start">
            <ExperimentOutlined style={{ fontSize: 24, color: '#2563eb' }} />
            <div>
              <Title level={3} style={{ marginTop: 0 }}>Pilot 试用与反馈 / Pilot & Feedback</Title>
              <Paragraph>
                这是小规模产品试用，不是自动求职服务。平台不会替你自动提交申请；系统识别或推测的内容，必须由你确认后才能成为个人事实。
              </Paragraph>
              <Paragraph type="secondary">
                This is a limited product pilot, not an auto-apply service. QLink never submits an application for you, and inferred information stays unconfirmed until you approve it.
              </Paragraph>
              <Tag color={state?.enrolled ? 'green' : 'default'}>
                {state?.enrolled ? '已参加 / Enrolled' : '未参加 / Not enrolled'}
              </Tag>
            </div>
          </Space>
        </Card>

        <Card title="开始前请确认 / Consent before testing">
          <Alert
            type="info"
            showIcon
            message="你可以正常使用产品而不参加研究，也可以随时退出。退出不会自动删除账号。"
            description="产品研究授权、汇总指标授权和模型改进授权彼此独立；模型改进默认关闭。"
            style={{ marginBottom: 16 }}
          />
          <Form form={consentForm} layout="vertical" onFinish={saveConsent}>
            <Form.Item name="product_research" valuePropName="checked">
              <Checkbox checked disabled>
                我自愿参加产品可用性试用，并提交我主动填写的反馈（必选）
              </Checkbox>
            </Form.Item>
            <Form.Item name="aggregate_metrics" label="允许使用去标识的汇总试用指标 / Aggregated metrics" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="model_improvement" label="允许将本次试用数据用于未来模型改进 / Model improvement (optional)" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Space wrap>
              <Button type="primary" htmlType="submit" loading={consentSaving}>
                {state?.enrolled ? '更新授权 / Update' : '同意并开始 / Join pilot'}
              </Button>
              {state?.enrolled && (
                <Button danger onClick={withdraw} loading={consentSaving}>退出 pilot / Withdraw</Button>
              )}
            </Space>
          </Form>
        </Card>

        <Card title="推荐试用路径 / Suggested test journey">
          <List
            dataSource={PILOT_STEPS}
            renderItem={(item, index) => <List.Item><Text strong>{index + 1}. {item}</Text></List.Item>}
          />
          <Button type="primary" onClick={() => navigate('/candidate/advisor')}>
            开始核心流程 / Start core workflow
          </Button>
        </Card>

        <Card title="提交反馈 / Share feedback">
          {!state?.enrolled && (
            <Alert type="warning" showIcon message="请先完成上方 pilot 授权，再提交试用反馈。" style={{ marginBottom: 16 }} />
          )}
          <Form
            form={feedbackForm}
            layout="vertical"
            disabled={!state?.enrolled}
            initialValues={{ category: 'usability', rating: 4, allow_follow_up: false }}
            onFinish={submitFeedback}
          >
            <Form.Item name="category" label="反馈类型" rules={[{ required: true }]}>
              <Select options={[
                { value: 'usability', label: '使用体验' },
                { value: 'trust', label: '信任与解释' },
                { value: 'recommendation', label: '建议质量' },
                { value: 'bug', label: '错误 / Bug' },
                { value: 'other', label: '其他' },
              ]} />
            </Form.Item>
            <Form.Item name="rating" label="整体评分" rules={[{ required: true }]}><Rate /></Form.Item>
            <Form.Item
              name="message"
              label="发生了什么？请勿填写身份证号、密码或其他敏感信息。"
              rules={[{ required: true, min: 1, max: 2000 }]}
            >
              <Input.TextArea rows={5} maxLength={2000} showCount />
            </Form.Item>
            <Form.Item name="allow_follow_up" valuePropName="checked">
              <Checkbox>允许维护者就这条反馈联系我</Checkbox>
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={feedbackSaving}>提交反馈</Button>
          </Form>
        </Card>

        <Card title={<span><SafetyCertificateOutlined /> 数据控制 / Data controls</span>}>
          <Paragraph>
            退出 pilot 只停止后续研究使用；删除账号会删除账号及其关联的私有数据，且无法恢复。
          </Paragraph>
          <Button danger icon={<DeleteOutlined />} onClick={() => setDeleteOpen(true)}>
            删除我的账号和数据
          </Button>
        </Card>
      </Space>

      <Modal
        title="永久删除账号和数据"
        open={deleteOpen}
        okText="确认永久删除"
        okButtonProps={{ danger: true, disabled: deletePhrase !== '删除我的账号', loading: deleteSaving }}
        cancelText="取消"
        onCancel={() => { setDeleteOpen(false); setDeletePhrase(''); }}
        onOk={deleteAccount}
      >
        <Paragraph type="danger">此操作无法撤销。请输入“删除我的账号”以确认。</Paragraph>
        <Input value={deletePhrase} onChange={(event) => setDeletePhrase(event.target.value)} />
      </Modal>
    </Spin>
  );
}

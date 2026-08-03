import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, Card, Empty, Form, Input, List, Modal, Popconfirm,
  Select, Space, Tag, Typography, Upload, message,
} from 'antd';
import { DeleteOutlined, DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import { createIdempotencyTracker } from '../../utils/idempotency';

const { Title, Paragraph, Text } = Typography;

export default function EvidenceVault() {
  const initIdempotency = useRef(createIdempotencyTracker('vault-init'));
  const uploadIdempotency = useRef(createIdempotencyTracker('vault-upload'));
  const withdrawIdempotency = useRef(createIdempotencyTracker('vault-withdraw'));
  const linkIdempotency = useRef(createIdempotencyTracker('vault-link'));
  const permissionIdempotency = useRef(createIdempotencyTracker('vault-permission'));
  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [claims, setClaims] = useState([]);
  const [linkArtifact, setLinkArtifact] = useState(null);
  const [linkForm] = Form.useForm();
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [response, overview] = await Promise.all([
        api.get('/evidence-vault/artifacts?limit=100'),
        api.get('/career-passport/overview'),
      ]);
      setArtifacts(response.data?.artifacts || []);
      setClaims(overview.data?.open_claims || []);
    } catch (error) {
      message.error(getApiErrorMessage(error, '经历材料库加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const create = async (values) => {
    const uploadRequired = !['user_statement', 'link'].includes(values.artifact_type);
    if (uploadRequired && !file) {
      message.error('当前材料类型需要选择一个支持的文档或代码文件；也可改选“用户说明/链接”免上传');
      return;
    }
    const initPayload = {
      artifact_type: values.artifact_type,
      title: values.title,
      source_url: values.source_url || null,
      issuer: values.issuer || null,
      allowed_uses: values.allowed_uses || ['resume_assistance'],
      default_visibility: values.default_visibility || 'private',
    };
    const initKey = initIdempotency.current.keyFor(initPayload);
    try {
      const initialized = await api.post('/evidence-vault/artifacts/init-upload', initPayload, {
        headers: { 'Idempotency-Key': initKey },
      });
      initIdempotency.current.complete(initKey);
      const artifact = initialized.data.artifact;
      if (initialized.data.upload_required) {
        const body = new FormData();
        body.append('file', file);
        const uploadKey = uploadIdempotency.current.keyFor({
          artifact_id: artifact.id,
          filename: file.name,
          size: file.size,
        });
        await api.post(`/evidence-vault/artifacts/${artifact.id}/complete-upload`, body, {
          headers: { 'Idempotency-Key': uploadKey },
        });
        uploadIdempotency.current.complete(uploadKey);
      }
      message.success('材料已安全保存');
      setOpen(false);
      setFile(null);
      form.resetFields();
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, '材料保存失败'));
    }
  };

  const withdraw = async (id) => {
    const idempotencyKey = withdrawIdempotency.current.keyFor({ artifact_id: id });
    try {
      await api.delete(`/evidence-vault/artifacts/${id}`, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      withdrawIdempotency.current.complete(idempotencyKey);
      message.success('材料已撤回，不能再用于新的改写');
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, '撤回失败'));
    }
  };

  const linkToClaim = async (values) => {
    const payload = {
      artifact_id: linkArtifact.id,
      relationship: values.relationship,
      access_scope: values.access_scope,
    };
    const idempotencyKey = linkIdempotency.current.keyFor({
      claim_id: values.claim_id,
      ...payload,
    });
    try {
      await api.post(`/evidence-vault/claims/${values.claim_id}/links`, payload, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      linkIdempotency.current.complete(idempotencyKey);
      message.success('材料已关联到对应经历细节');
      setLinkArtifact(null);
      linkForm.resetFields();
    } catch (error) {
      message.error(getApiErrorMessage(error, '绑定失败'));
    }
  };

  const toggleShare = async (item) => {
    const share = item.default_visibility === 'private';
    const payload = {
      allowed_uses: share
        ? Array.from(new Set([...(item.allowed_uses || []), 'application_share']))
        : (item.allowed_uses || []).filter((value) => value !== 'application_share'),
      default_visibility: share ? 'application_selected' : 'private',
    };
    const idempotencyKey = permissionIdempotency.current.keyFor({
      artifact_id: item.id,
      ...payload,
    });
    try {
      await api.patch(`/evidence-vault/artifacts/${item.id}/permissions`, payload, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      permissionIdempotency.current.complete(idempotencyKey);
      message.success(share ? '已设为投递时可选择分享' : '已恢复为仅自己可见');
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, '权限更新失败'));
    }
  };

  const downloadArtifact = async (item) => {
    try {
      const response = await api.get(`/evidence-vault/artifacts/${item.id}/download-url`);
      const url = response.data?.url;
      if (!url) {
        message.error('无法生成下载链接');
        return;
      }
      const absolute = url.startsWith('http') ? url : `${api.defaults.baseURL}${url}`;
      window.open(absolute, '_blank', 'noopener,noreferrer');
    } catch (error) {
      message.error(getApiErrorMessage(error, '获取下载链接失败'));
    }
  };

  return (
    <div>
      <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>经历材料库（可选补充）</Title>
          <Paragraph type="secondary">优先用一句话说明或作品链接补充上下文；只有确实需要展示原件时才上传文件，默认只有你能看到。</Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加说明、链接或文件</Button>
      </Space>
      <Alert
        type="info"
        showIcon
        message="它有什么用？"
        description="不是每条经历都需要证明材料。你可以只写一条个人说明，或粘贴 GitHub、作品集、报告链接；文件上传完全可选。材料不会自动分享给招聘方，撤回后不会进入新的改写。请勿上传身份证、工资单等高敏感原件。"
        style={{ marginBottom: 16 }}
      />
      <Card loading={loading}>
        {artifacts.length ? (
          <List
            dataSource={artifacts}
            renderItem={(item) => (
              <List.Item
                actions={[
                  item.has_file ? (
                    <Button key="download" type="link" icon={<DownloadOutlined />} onClick={() => downloadArtifact(item)}>
                      短时下载
                    </Button>
                  ) : null,
                  <Button key="link" type="link" onClick={() => setLinkArtifact(item)}>绑定 Claim</Button>,
                  <Button key="share" type="link" onClick={() => toggleShare(item)}>
                    {item.default_visibility === 'private' ? '投递时可选分享' : '恢复仅自己'}
                  </Button>,
                  <Popconfirm key="withdraw" title="撤回后不能再用于新的改写，确认撤回？" onConfirm={() => withdraw(item.id)}>
                    <Button danger type="text" icon={<DeleteOutlined />}>撤回</Button>
                  </Popconfirm>,
                ].filter(Boolean)}
              >
                <List.Item.Meta
                  title={<Space wrap><span>{item.title}</span><Tag>{item.artifact_type}</Tag><Tag>{item.verification_status === 'third_party_verified' ? '第三方已验证' : '用户提供'}</Tag></Space>}
                  description={(
                    <Space direction="vertical" size={2}>
                      <Text type="secondary">可见范围：{item.default_visibility === 'private' ? '仅自己' : '投递时选择'}</Text>
                      <Text type="secondary">用途：{(item.allowed_uses || []).join('、') || '未授权'}</Text>
                      {item.content_hash && <Text code>{item.content_hash.slice(0, 16)}…</Text>}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        ) : <Empty description="无需为了使用职业档案而上传材料；需要补充某条经历时，再添加说明或链接即可" />}
      </Card>

      <Modal title="补充经历依据（可选）" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={create} initialValues={{ artifact_type: 'user_statement', allowed_uses: ['resume_assistance'], default_visibility: 'private' }}>
          <Form.Item name="artifact_type" label="材料类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'user_statement', label: '用户说明（无需文件）' },
              { value: 'link', label: '链接（无需文件）' },
              { value: 'document', label: '文档' },
              { value: 'code', label: '代码文件（Python / Notebook 等）' },
              { value: 'certificate', label: '证书' },
              { value: 'sample', label: '作品样本' },
            ]} />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input maxLength={255} /></Form.Item>
          <Form.Item name="source_url" label="来源链接"><Input type="url" /></Form.Item>
          <Form.Item name="issuer" label="签发者/来源组织"><Input maxLength={255} /></Form.Item>
          <Form.Item name="allowed_uses" label="允许用途">
            <Select mode="multiple" options={[
              { value: 'resume_assistance', label: '简历辅助' },
              { value: 'application_share', label: '投递时可选分享' },
              { value: 'model_improvement', label: '模型改进（单独授权）' },
            ]} />
          </Form.Item>
          <Form.Item name="default_visibility" label="默认可见范围">
            <Select options={[
              { value: 'private', label: '仅自己' },
              { value: 'application_selected', label: '投递时选择' },
            ]} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="选择“用户说明”或“链接”时无需上传文件。"
          />
          <Upload
            beforeUpload={(selected) => { setFile(selected); return false; }}
            maxCount={1}
            accept=".pdf,.docx,.txt,.md,.py,.ipynb,.js,.ts,.java,.go,.rs,.sql,.csv"
          >
            <Button icon={<UploadOutlined />}>选择文件（仅在需要时）</Button>
          </Upload>
          <Button type="primary" htmlType="submit" block style={{ marginTop: 20 }}>
            保存材料
          </Button>
        </Form>
      </Modal>
      <Modal title={`关联到经历细节：${linkArtifact?.title || ''}`} open={Boolean(linkArtifact)} onCancel={() => setLinkArtifact(null)} footer={null} destroyOnHidden>
        <Form form={linkForm} layout="vertical" onFinish={linkToClaim} initialValues={{ relationship: 'supports', access_scope: 'private' }}>
          <Form.Item name="claim_id" label="目标 Claim" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={claims.map((claim) => ({ value: claim.id, label: claim.text }))}
              notFoundContent="请先在职业档案中创建或同步 Claim"
            />
          </Form.Item>
          <Form.Item name="relationship" label="关系">
            <Select options={[
              { value: 'supports', label: '支持' },
              { value: 'contradicts', label: '存在待澄清的不一致' },
              { value: 'related', label: '相关' },
            ]} />
          </Form.Item>
          <Form.Item name="access_scope" label="此关系的访问范围">
            <Select options={[
              { value: 'private', label: '仅自己' },
              { value: 'application_selected', label: '投递时选择' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>确认绑定</Button>
        </Form>
      </Modal>
    </div>
  );
}

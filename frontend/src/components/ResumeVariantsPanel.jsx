import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Input, List, Modal, Select, Space, Spin, Tag, Typography, message,
} from 'antd';
import {
  CopyOutlined, DeleteOutlined, EyeOutlined, SwapOutlined,
} from '@ant-design/icons';
import api from '../api';
import ResumeDocumentView from './ResumeDocumentView';

const { Text, Paragraph } = Typography;

export default function ResumeVariantsPanel({
  resumeId,
  defaultJobTitle = '',
  topMatches = [],
  onApplyVariant,
}) {
  const [templates, setTemplates] = useState([]);
  const [variants, setVariants] = useState([]);
  const [targetJobTitle, setTargetJobTitle] = useState(defaultJobTitle);
  const [styleTemplate, setStyleTemplate] = useState('balanced');
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewVariant, setPreviewVariant] = useState(null);

  const fetchVariants = async () => {
    if (!resumeId) return;
    setLoading(true);
    try {
      const res = await api.get(`/resumes/${resumeId}/variants`);
      setVariants(res.data?.variants || []);
    } catch {
      setVariants([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.get('/resume-variant-templates')
      .then((res) => setTemplates(res.data?.templates || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setTargetJobTitle(defaultJobTitle || '');
    setVariants([]);
    if (resumeId) fetchVariants();
  }, [resumeId, defaultJobTitle]);

  const handleGenerate = async () => {
    if (!targetJobTitle.trim()) {
      message.warning('请输入目标岗位名称，如 Java 后端');
      return;
    }
    setGenerating(true);
    try {
      const res = await api.post(`/resumes/${resumeId}/variants/generate`, {
        target_job_title: targetJobTitle.trim(),
        style_template: styleTemplate,
        job_id: selectedJobId || undefined,
      });
      message.success(`已生成「${res.data.variant.label}」`);
      await fetchVariants();
      setPreviewVariant(res.data.variant);
    } catch (err) {
      message.error(err.response?.data?.detail || '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const handlePreview = async (variantId) => {
    try {
      const res = await api.get(`/resumes/${resumeId}/variants/${variantId}`);
      setPreviewVariant(res.data);
    } catch {
      message.error('加载定制版失败');
    }
  };

  const handleApply = async (variantId) => {
    try {
      const res = await api.post(`/resumes/${resumeId}/variants/apply`, {
        variant_id: variantId,
      });
      message.success(`已将「${res.data.variant_label}」应用到主简历`);
      onApplyVariant?.(res.data);
    } catch {
      message.error('应用失败');
    }
  };

  const handleDelete = async (variantId) => {
    Modal.confirm({
      title: '删除定制版',
      content: '确定删除该岗位定制版吗？',
      onOk: async () => {
        try {
          await api.delete(`/resumes/${resumeId}/variants/${variantId}`);
          message.success('已删除');
          if (previewVariant?.id === variantId) setPreviewVariant(null);
          await fetchVariants();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  return (
    <>
      <Card size="small" title={<><CopyOutlined /> 岗位定制版</>} style={{ marginTop: 12 }}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12, fontSize: 13 }}
          message="基于同一份简历生成目标岗位版本，如「Java 后端版」"
        />

        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>目标岗位</Text>
            <Input
              style={{ marginTop: 4 }}
              placeholder="如 Java 后端、产品经理"
              value={targetJobTitle}
              onChange={(e) => setTargetJobTitle(e.target.value)}
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>风格模板（5 种）</Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              value={styleTemplate}
              onChange={setStyleTemplate}
              options={templates.map((t) => ({
                value: t.id,
                label: `${t.label} — ${t.description}`,
              }))}
            />
          </div>
          {topMatches.length > 0 && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>参考匹配岗位（可选）</Text>
              <Select
                allowClear
                placeholder="选择 Top 匹配岗位"
                style={{ width: '100%', marginTop: 4 }}
                value={selectedJobId}
                onChange={setSelectedJobId}
                options={topMatches.map((m) => ({
                  value: m.job_id,
                  label: `${m.job_title} (${Number(m.score).toFixed(1)}分)`,
                }))}
              />
            </div>
          )}
          <Button type="primary" loading={generating} onClick={handleGenerate} block>
            生成岗位定制版
          </Button>
        </Space>

        <Spin spinning={loading}>
          {variants.length > 0 && (
            <List
              size="small"
              style={{ marginTop: 12 }}
              dataSource={variants}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="view"
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => handlePreview(item.id)}
                    >
                      预览
                    </Button>,
                    <Button
                      key="apply"
                      type="link"
                      size="small"
                      icon={<SwapOutlined />}
                      onClick={() => handleApply(item.id)}
                    >
                      应用
                    </Button>,
                    <Button
                      key="del"
                      type="link"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDelete(item.id)}
                    />,
                  ]}
                >
                  <List.Item.Meta
                    title={(
                      <Space>
                        <Text strong style={{ fontSize: 13 }}>{item.label}</Text>
                        <Tag>{item.style_template}</Tag>
                      </Space>
                    )}
                    description={(
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {item.target_job_title}
                        {item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ''}
                      </Text>
                    )}
                  />
                </List.Item>
              )}
            />
          )}
          {variants.length === 0 && !loading && (
            <Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
              暂无定制版，输入岗位名称后点击生成
            </Paragraph>
          )}
        </Spin>
      </Card>

      <Modal
        title={previewVariant?.label || '定制版预览'}
        open={!!previewVariant}
        onCancel={() => setPreviewVariant(null)}
        width={640}
        footer={previewVariant?.id ? (
          <Space>
            <Button onClick={() => setPreviewVariant(null)}>关闭</Button>
            <Button
              type="primary"
              icon={<SwapOutlined />}
              onClick={() => {
                handleApply(previewVariant.id);
                setPreviewVariant(null);
              }}
            >
              应用到主简历
            </Button>
          </Space>
        ) : null}
      >
        {previewVariant?.parsed_json && (
          <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
            <ResumeDocumentView parsed={previewVariant.parsed_json} />
          </div>
        )}
      </Modal>
    </>
  );
}

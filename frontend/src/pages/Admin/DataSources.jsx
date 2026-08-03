import { useEffect, useState } from 'react';
import { Alert, Card, Table, Tag, Typography, message } from 'antd';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';

const { Title, Paragraph } = Typography;

const STATUS_COLOR = {
  approved: 'green',
  pending_review: 'gold',
  restricted: 'orange',
  revoked: 'red',
};

/**
 * Admin-facing data source status (no contract secrets).
 */
export default function AdminDataSources() {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .get('/admin/data-sources')
      .then((res) => setSources(res.data?.sources || []))
      .catch((err) => message.error(getApiErrorMessage(err, '无法加载数据来源')))
      .finally(() => setLoading(false));
  }, []);

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '层级',
      dataIndex: 'layer',
      key: 'layer',
      render: (layer) => (
        <Tag color={layer === 'E' ? 'default' : 'blue'}>
          {layer}
          {layer === 'E' ? '（非正式画像）' : ''}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => <Tag color={STATUS_COLOR[status] || 'default'}>{status}</Tag>,
    },
    { title: '获取方式', dataIndex: 'acquisition_method', key: 'acquisition_method' },
    { title: '处理地域', dataIndex: 'processing_region', key: 'processing_region' },
    {
      title: '允许用途',
      dataIndex: 'allowed_product_uses',
      key: 'allowed_product_uses',
      render: (uses) => (uses || []).join('、') || '—',
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>数据来源登记</Title>
      <Paragraph type="secondary">
        仅展示状态与用途摘要，不展示合同正文。pending_review / revoked / E 层来源不得进入正式岗位画像。
      </Paragraph>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="论坛统计为 E 层定性线索，不能作为企业录用偏好。"
      />
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={sources}
          pagination={false}
        />
      </Card>
    </div>
  );
}

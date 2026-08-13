import { Alert, Card, List, Space, Tag, Typography } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { formatOutcomeTime, getOutcomeSourceConfig } from '../utils/applicationTimeline';

const { Text, Paragraph } = Typography;

export default function OutcomeRecommendationChange({ changes = [] }) {
  const latest = Array.isArray(changes) ? changes.at(-1) : null;
  if (!latest) return null;
  const source = getOutcomeSourceConfig(latest.source);

  return (
    <Card size="small" title="这次建议为什么变化" style={{ marginTop: 16 }}>
      <Space wrap size={6} style={{ marginBottom: 10 }}>
        <Tag color={source.color}>{source.label}</Tag>
        <Text>{latest.trigger_label || latest.trigger_status}</Text>
        <Text type="secondary">{formatOutcomeTime(latest.occurred_at)}</Text>
      </Space>
      <div style={{ marginBottom: 10 }}>
        <Text type="secondary">之前重点</Text>
        <div>{latest.previous_priority}</div>
      </div>
      <Space align="start" style={{ marginBottom: 10 }}>
        <ArrowRightOutlined style={{ marginTop: 4 }} />
        <div>
          <Text type="secondary">现在重点</Text>
          <div><Text strong>{latest.current_priority}</Text></div>
        </div>
      </Space>
      <Paragraph>{latest.why}</Paragraph>
      <Alert
        type="info"
        showIcon
        message="没有改变的事实边界"
        description={(
          <List
            size="small"
            split={false}
            dataSource={latest.unchanged_boundaries || []}
            renderItem={(item) => <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>}
          />
        )}
      />
    </Card>
  );
}

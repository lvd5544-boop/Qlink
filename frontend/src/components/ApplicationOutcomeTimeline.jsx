import { Card, Empty, Space, Tag, Timeline, Typography } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import {
  formatOutcomeTime,
  normalizeOutcomeTimeline,
} from '../utils/applicationTimeline';

const { Text, Paragraph } = Typography;

export default function ApplicationOutcomeTimeline({ events = [], title = '申请结果时间线' }) {
  const timeline = normalizeOutcomeTimeline(events);

  return (
    <Card size="small" title={title} style={{ marginTop: 16 }}>
      {timeline.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有结果记录" />
      ) : (
        <Timeline
          items={timeline.map((event) => ({
            color: event.sourceConfig.color,
            dot: <ClockCircleOutlined />,
            children: (
              <div>
                <Space wrap size={6}>
                  <Text strong>{event.label}</Text>
                  <Tag color={event.sourceConfig.color}>{event.sourceConfig.label}</Tag>
                </Space>
                <div>
                  <Text type="secondary">发生：{formatOutcomeTime(event.occurredAt)}</Text>
                </div>
                {event.recordedAt && event.recordedAt !== event.occurredAt && (
                  <div>
                    <Text type="secondary">记录：{formatOutcomeTime(event.recordedAt)}</Text>
                  </div>
                )}
                {event.feedback && (
                  <Paragraph style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>
                    原始反馈：{event.feedback}
                  </Paragraph>
                )}
              </div>
            ),
          }))}
        />
      )}
      <Text type="secondary" style={{ fontSize: 12 }}>
        时间线只记录来源和结果；未通过且没有具体反馈时，不会自动生成新的能力缺口。
      </Text>
    </Card>
  );
}

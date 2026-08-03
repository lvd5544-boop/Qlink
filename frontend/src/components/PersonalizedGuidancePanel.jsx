import {
  Alert, List, Space, Tag, Typography,
} from 'antd';

const { Text } = Typography;

export default function PersonalizedGuidancePanel({
  guidance,
  fallback = [],
  title = '为你排序的下一步',
}) {
  const actions = guidance?.actions || [];
  return (
    <div>
      <Text strong>{title}</Text>
      {guidance?.focus && (
        <Alert
          style={{ marginTop: 8 }}
          type="info"
          showIcon
          message={guidance.focus}
        />
      )}
      <List
        size="small"
        dataSource={actions.length ? actions : fallback}
        renderItem={(item, index) => (
          <List.Item>
            {typeof item === 'string' ? item : (
              <List.Item.Meta
                title={(
                  <Space wrap>
                    <Tag color="blue">优先级 {item.priority || index + 1}</Tag>
                    <Text strong>{item.title}</Text>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={3}>
                    <Text>{item.why_for_you}</Text>
                    {item.start_from && <Text type="secondary">从你的「{item.start_from}」经历开始</Text>}
                    {item.first_step && <Text>第一步：{item.first_step}</Text>}
                    {(item.success_criteria || []).length > 0 && (
                      <Text type="success">完成标准：{item.success_criteria.join('；')}</Text>
                    )}
                  </Space>
                )}
              />
            )}
          </List.Item>
        )}
      />
    </div>
  );
}

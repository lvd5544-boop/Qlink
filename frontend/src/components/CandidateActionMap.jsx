import {
  Alert, Button, Card, Empty, List, Space, Tag, Typography,
} from 'antd';

const { Text } = Typography;

const GROUP_META = {
  ready: {
    title: '已有事实，可立即优化',
    color: 'success',
    description: '这些建议已经关联到你提供的经历，可先用于忠实改写或申请表达。',
  },
  clarify: {
    title: '需要说清楚',
    color: 'processing',
    description: '存在相关线索，但角色、方法、范围、结果或证据仍不完整。',
  },
  develop: {
    title: '建议提升，先由你确认',
    color: 'warning',
    description: '这不是“你不会”的结论；先确认确实没有相关经历，再决定是否投入行动。',
  },
  constraint: {
    title: '现实条件需要确认',
    color: 'error',
    description: '地点、学历、证书或工作方式等条件应与能力分开处理。',
  },
  unknown: {
    title: '暂时无法可靠判断',
    color: 'default',
    description: '当前材料不足，不强行判断；可以补充经历、证据或直接询问岗位方。',
  },
};

function recommendedStrategy(issue) {
  return (issue.strategies || []).find((item) => item.recommended)
    || issue.strategies?.[0]
    || null;
}

function groupFor(issue) {
  if (issue.category === 'hard_constraint') return 'constraint';
  if (issue.category === 'capability') return 'develop';
  const strategy = recommendedStrategy(issue);
  if ((issue.claim_ids || []).length > 0 && strategy?.can_apply_now) return 'ready';
  if (['expression', 'evidence', 'consistency', 'relevance', 'differentiation', 'career_narrative'].includes(issue.category)) {
    return 'clarify';
  }
  return 'unknown';
}

export default function CandidateActionMap({ diagnostic, onResolveIssue }) {
  const grouped = Object.fromEntries(Object.keys(GROUP_META).map((key) => [key, []]));
  for (const issue of diagnostic?.issues || []) grouped[groupFor(issue)].push(issue);
  const visibleGroups = Object.entries(GROUP_META).filter(([key]) => grouped[key].length > 0);

  if (!visibleGroups.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有足够信息形成行动地图" />;
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Alert
        showIcon
        type="info"
        message="先处理能改变这次申请的事项"
        description="系统只整理你已提供的事实和信息缺口；没有写出来不等于没有能力。"
      />
      {visibleGroups.map(([key, meta]) => (
        <Card
          key={key}
          size="small"
          title={(
            <Space wrap>
              <Tag color={meta.color}>{grouped[key].length}</Tag>
              <Text strong>{meta.title}</Text>
            </Space>
          )}
        >
          <Text type="secondary">{meta.description}</Text>
          {key === 'clarify' && grouped[key].length > 3 && (
            <Alert
              type="info"
              message={`先回答最重要的 3 个问题，其余 ${grouped[key].length - 3} 项稍后处理`}
              style={{ marginTop: 8 }}
            />
          )}
          <List
            style={{ marginTop: 8 }}
            size="small"
            dataSource={key === 'clarify' ? grouped[key].slice(0, 3) : grouped[key]}
            renderItem={(issue) => {
              const strategy = recommendedStrategy(issue);
              return (
                <List.Item>
                  <List.Item.Meta
                    title={issue.diagnosis}
                    description={(
                      <Space direction="vertical" size={2}>
                        {(issue.claim_ids || []).length > 0 && (
                          <Text type="secondary">已关联你的经历 {issue.claim_ids.length} 条</Text>
                        )}
                        {strategy?.title && <Text>建议下一步：{strategy.title}</Text>}
                        {strategy?.next_action && <Text type="secondary">{strategy.next_action}</Text>}
                        {key === 'clarify' && (
                          <Button size="small" onClick={() => onResolveIssue?.(issue)}>
                            补充这条经历或证据
                          </Button>
                        )}
                      </Space>
                    )}
                  />
                </List.Item>
              );
            }}
          />
        </Card>
      ))}
    </Space>
  );
}

import { Button, Card, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const statusMeta = {
  hypothesis: { label: '待你验证', color: 'processing' },
  user_confirmed: { label: '本人确认', color: 'green' },
  evidence_supported: { label: '已有证据支持', color: 'success' },
  rejected: { label: '已排除', color: 'default' },
};

export default function HypothesisReviewList({ hypotheses = [], onStatusChange }) {
  if (!hypotheses.length) return null;
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Text strong>待验证的可能性（最多两条）</Text>
      {hypotheses.map((hypothesis) => {
        const meta = statusMeta[hypothesis.status] || statusMeta.hypothesis;
        return (
          <Card key={hypothesis.id} size="small" data-testid={`c5-hypothesis-${hypothesis.id}`}>
            <Space wrap>
              <Tag color={meta.color}>{meta.label}</Tag>
              <Text type="secondary">规则 {hypothesis.rule_version}</Text>
            </Space>
            <Paragraph style={{ margin: '8px 0 4px' }}>{hypothesis.text}</Paragraph>
            <Paragraph type="secondary" style={{ marginBottom: 8 }}>
              请确认：{hypothesis.validation_question}
            </Paragraph>
            {hypothesis.status === 'hypothesis' && (
              <Space wrap>
                <Button
                  size="small"
                  type="primary"
                  onClick={() => onStatusChange?.(hypothesis, 'user_confirmed')}
                >
                  是，我有这段经历
                </Button>
                <Button size="small" onClick={() => onStatusChange?.(hypothesis, 'rejected')}>
                  不适用
                </Button>
              </Space>
            )}
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              本次选择只更新假设状态，不会自动写入简历或作为招聘结论。
            </Text>
          </Card>
        );
      })}
    </Space>
  );
}

import { useState } from 'react';
import { Progress, Alert, Row, Col, Tag, Space, Typography } from 'antd';
import { CheckCircleOutlined, RightOutlined } from '@ant-design/icons';
import SuggestionDiffCard from './SuggestionDiffCard';
import HealthScoreDetailModal from './HealthScoreDetailModal';

const { Text } = Typography;

function ClickableScoreRing({
  percent,
  label,
  strokeColor,
  size,
  onClick,
}) {
  return (
    <div
      style={{ textAlign: 'center', cursor: onClick ? 'pointer' : 'default' }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      <Progress
        type="circle"
        percent={percent}
        size={size}
        strokeColor={strokeColor}
        style={onClick ? { transition: 'transform 0.15s' } : undefined}
      />
      <div style={{ marginTop: 8, color: '#64748b', fontSize: 13 }}>
        {label}
        {onClick && (
          <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 2 }}>
            点击查看详情 <RightOutlined style={{ fontSize: 10 }} />
          </Text>
        )}
      </div>
    </div>
  );
}

export default function ResumeHealthPanel({
  healthCheck,
  actionableSuggestions = [],
  resumeId = null,
  onApplySuggestion,
  onDismissSuggestion,
  applyingId = null,
  compact = false,
}) {
  const [detailType, setDetailType] = useState(null);

  if (!healthCheck) {
    return (
      <Alert
        type="warning"
        showIcon
        message="暂无体检数据"
        description="可点击「重新体检」生成完整度与量化分析"
      />
    );
  }

  const actions = (actionableSuggestions.length
    ? actionableSuggestions
    : healthCheck.actionable_suggestions || [])
    .filter((s) => s.source !== 'coach');

  const circleSize = compact ? 64 : 80;

  const overallDetail = healthCheck.overall_detail || {
    score: healthCheck.overall_score,
    strengths: [],
    weaknesses: [],
    formula: '综合得分 = 完整度 × 60% + 量化程度 × 40%',
  };

  const completenessDetail = healthCheck.completeness_detail || {
    score: healthCheck.completeness?.score,
    strengths: (healthCheck.completeness?.fields
      ? Object.values(healthCheck.completeness.fields)
        .filter((f) => f.filled)
        .map((f) => ({ title: f.label, detail: '已填写' }))
      : []),
    weaknesses: (healthCheck.completeness?.missing || []).map((m) => ({
      title: m,
      detail: '未填写，建议补充',
    })),
  };

  const detailMap = {
    overall: { title: '综合得分明细', data: overallDetail },
    completeness: { title: '完整度评分明细', data: completenessDetail },
  };

  const activeDetail = detailType ? detailMap[detailType] : null;

  return (
    <div>
      <Row gutter={16}>
        <Col xs={8}>
          <ClickableScoreRing
            percent={healthCheck.overall_score}
            label="综合得分"
            size={circleSize}
            onClick={() => setDetailType('overall')}
          />
        </Col>
        <Col xs={8}>
          <ClickableScoreRing
            percent={healthCheck.completeness?.score}
            label="完整度"
            strokeColor="#10b981"
            size={circleSize}
            onClick={() => setDetailType('completeness')}
          />
        </Col>
        <Col xs={8}>
          <ClickableScoreRing
            percent={healthCheck.quantification?.score}
            label="量化程度"
            strokeColor="#f59e0b"
            size={circleSize}
          />
        </Col>
      </Row>

      {healthCheck.completeness?.missing?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">缺失项：</Text>
          <Space wrap style={{ marginTop: 4 }}>
            {healthCheck.completeness.missing.map((item) => (
              <Tag key={item} color="orange">{item}</Tag>
            ))}
          </Space>
        </div>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <Text strong style={{ fontSize: 15 }}>逐条对比与采纳</Text>
          <Text type="secondary" style={{ display: 'block', fontSize: 13, marginBottom: 12 }}>
            原文与修改版对照，可编辑后采纳
          </Text>
          {actions.map((item) => (
            <SuggestionDiffCard
              key={item.id}
              suggestion={item}
              resumeId={resumeId}
              loading={applyingId === item.id}
              onAccept={onApplySuggestion}
              onDismiss={onDismissSuggestion}
            />
          ))}
        </div>
      )}

      {actions.length === 0 && (
        <Alert style={{ marginTop: 16 }} type="info" showIcon message="体检建议已全部处理，可运行 AI 诊断获取更多建议" />
      )}

      {healthCheck.checked_at && (
        <Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
          <CheckCircleOutlined /> 体检时间：{new Date(healthCheck.checked_at).toLocaleString()}
        </Text>
      )}

      <HealthScoreDetailModal
        open={!!activeDetail}
        onClose={() => setDetailType(null)}
        title={activeDetail?.title}
        detail={activeDetail?.data}
      />
    </div>
  );
}

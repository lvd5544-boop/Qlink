import { useState } from 'react';
import { Progress, Alert, Row, Col, Tag, Space, Typography, Card } from 'antd';
import { CheckCircleOutlined, RightOutlined, EditOutlined } from '@ant-design/icons';
import SuggestionDiffCard from './SuggestionDiffCard';
import HealthScoreDetailModal from './HealthScoreDetailModal';

const { Text } = Typography;

function isConsistencySuggestion(suggestion) {
  if (!suggestion) return false;
  if (suggestion.source === 'consistency') return true;
  const key = suggestion.id || suggestion.suggestion_key || '';
  return String(key).startsWith('consistency_');
}

function mergeActionableSuggestions(pending, healthCheck) {
  const fromPending = pending?.length ? pending : [];
  const fromHealth = healthCheck?.actionable_suggestions || [];
  const byId = new Map();
  [...fromPending, ...fromHealth].forEach((item) => {
    if (!item || item.source === 'coach') return;
    const id = item.id || item.suggestion_key;
    if (!id) return;
    if (!byId.has(id) || isConsistencySuggestion(item)) {
      byId.set(id, item);
    }
  });
  return [...byId.values()];
}

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

  const actions = mergeActionableSuggestions(actionableSuggestions, healthCheck);

  const consistencyIssues = healthCheck.consistency_diagnosis?.issues || [];
  const consistencyActions = actions.filter((s) => isConsistencySuggestion(s));
  const otherActions = actions.filter((s) => !isConsistencySuggestion(s));
  const needsConsistencyRefresh = !healthCheck.consistency_diagnosis;

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

  const unquantified = healthCheck.quantification?.unquantified_entries || [];

  const consistencyActionIssueIds = new Set(
    consistencyActions.map((a) => String(a.id || '').replace(/^consistency_/, '')),
  );
  const consistencyIssuesWithoutActions = consistencyIssues.filter(
    (item) => !consistencyActionIssueIds.has(item.id),
  );

  const totalDiagnosisCount = otherActions.length
    + consistencyActions.length
    + consistencyIssuesWithoutActions.length;

  const hasDiagnosisContent = totalDiagnosisCount > 0;

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

      {needsConsistencyRefresh && (
        <Alert
          style={{ marginTop: 16 }}
          type="warning"
          showIcon
          message="表述一致性分析未加载"
          description="请点击上方「重新体检」，生成「表述一致性提醒」与可采纳的改稿建议。"
        />
      )}

      {healthCheck.completeness?.missing?.length > 0 && !hasDiagnosisContent && (
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">缺失项：</Text>
          <Space wrap style={{ marginTop: 4 }}>
            {healthCheck.completeness.missing.map((item) => (
              <Tag key={item} color="orange">{item}</Tag>
            ))}
          </Space>
        </div>
      )}

      {hasDiagnosisContent && (
        <Card
          size="small"
          style={{ marginTop: 16, borderColor: '#fcd34d', background: '#fffbeb' }}
          title={(
            <Space>
              <EditOutlined style={{ color: '#d97706' }} />
              诊断与采纳
              <Tag color="orange">{totalDiagnosisCount}</Tag>
            </Space>
          )}
        >
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16, fontSize: 12, background: '#fef3c7', border: '1px solid #fcd34d' }}
            message={(
              <>
                共发现 {totalDiagnosisCount} 项待处理问题
                {unquantified.length > 0 && (
                  <>，其中 {unquantified.length} 段经历缺少量化数据</>
                )}
                {consistencyIssues.length > 0 && (
                  <>，{consistencyIssues.length} 处表述一致性问题</>
                )}
              </>
            )}
            description="下方按类别列出全部诊断结果，可预览修改建议后采纳或忽略；缺少量化数据时可使用「AI 追问」补充真实数据"
          />

          {(consistencyIssues.length > 0 || consistencyActions.length > 0) && (
            <div style={{ marginBottom: otherActions.length > 0 ? 20 : 0 }}>
              <Space style={{ marginBottom: 12 }}>
                <Tag color="gold">表述一致性</Tag>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {consistencyActions.length + consistencyIssuesWithoutActions.length} 项
                </Text>
              </Space>

              {healthCheck.consistency_diagnosis?.summary && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12, fontSize: 12 }}
                  message={healthCheck.consistency_diagnosis.summary}
                  description={healthCheck.consistency_diagnosis.disclaimer}
                />
              )}

              {consistencyIssuesWithoutActions.map((item) => (
                <div
                  key={item.id}
                  style={{
                    padding: 10,
                    marginBottom: 12,
                    borderRadius: 8,
                    border: '1px solid #fde68a',
                    background: '#fff',
                  }}
                >
                  <Space wrap style={{ marginBottom: 4 }}>
                    <Tag color={item.severity === 'medium' ? 'orange' : 'default'}>
                      {item.category}
                    </Tag>
                    <Text strong style={{ fontSize: 13 }}>{item.title}</Text>
                  </Space>
                  <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                    <Text type="secondary">检测到：</Text>{item.detected}
                  </div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>
                    <Text type="secondary">为何建议修改：</Text>{item.why}
                  </div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>
                    <Text type="secondary">改稿建议：</Text>{item.wording_fix}
                  </div>
                  {item.clarification_question && (
                    <div style={{
                      marginTop: 6, padding: '8px 10px', borderRadius: 6,
                      background: '#fff7ed', border: '1px solid #fed7aa', fontSize: 12,
                    }}
                    >
                      <Text type="secondary">需先确认：</Text>
                      {item.clarification_question}
                    </div>
                  )}
                  {item.example_rewrite && (
                    <div style={{
                      marginTop: 6, padding: '8px 10px', borderRadius: 6,
                      background: '#ecfdf5', border: '1px solid #a7f3d0', fontSize: 12,
                    }}
                    >
                      <Text type="secondary">示例写法：</Text>
                      {item.example_rewrite}
                    </div>
                  )}
                </div>
              ))}

              {consistencyActions.map((item) => (
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

          {otherActions.length > 0 && (
            <div>
              <Space style={{ marginBottom: 12 }}>
                <Tag color="orange">完整度与量化</Tag>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {otherActions.length} 项
                </Text>
              </Space>
              {otherActions.map((item) => (
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
        </Card>
      )}

      {!hasDiagnosisContent && !needsConsistencyRefresh && (
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

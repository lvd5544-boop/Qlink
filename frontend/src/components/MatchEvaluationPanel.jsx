import { Progress, Tag, Space, Typography, Divider, List, Alert } from 'antd';
import {
  RocketOutlined,
  BulbOutlined,
  ProjectOutlined,
  BankOutlined,
} from '@ant-design/icons';
import { ClickableScoreTag } from './ScoreRulesPopover';
import { resolveMatchBreakdown, resolveMatchReason, filterSoftSkillsForDisplay } from '../utils/matchBreakdown';

const { Text, Paragraph } = Typography;

const DIMENSION_LABELS = {
  skills: '技能匹配',
  experience: '经验年限',
  role_match: '职位方向',
  industry_match: '行业匹配',
  education: '学历',
  location: '地点',
  salary: '薪资',
  impact: '项目影响力',
  soft_skills: '软实力',
  growth_potential: '成长潜力',
};

function scoreColor(ratio) {
  if (ratio >= 0.8) return '#10b981';
  if (ratio >= 0.5) return '#f59e0b';
  return '#ef4444';
}

function tierTag(tier) {
  if (tier === 'high') return <Tag color="success">高匹配</Tag>;
  if (tier === 'medium') return <Tag color="warning">中匹配</Tag>;
  return <Tag color="error">低匹配</Tag>;
}

export default function MatchEvaluationPanel({ evaluation }) {
  if (!evaluation) {
    return <Alert type="info" message="暂无评分数据，请确认已上传简历" showIcon />;
  }

  const { breakdown: rawBreakdown, signals, career_suggestions: cs } = evaluation;
  const apiBreakdown = evaluation.api_breakdown || resolveMatchBreakdown({
    breakdown: evaluation.api_breakdown,
    score_breakdown: rawBreakdown,
  });
  const version = apiBreakdown?.version ?? rawBreakdown?.version ?? 2;
  const displayReason = resolveMatchReason({
    reason: evaluation.reason,
    score_breakdown: rawBreakdown,
    score: evaluation.match_score,
  });

  const dimensions = apiBreakdown?.dimensions?.length
    ? apiBreakdown.dimensions.map((d) => ({
        key: d.key,
        label: d.label,
        ratio: d.ratio ?? 0,
        score: d.score,
        weight: d.weight,
      }))
    : Object.entries(DIMENSION_LABELS).map(([key, label]) => {
        const dim = rawBreakdown?.[key];
        if (!dim) return null;
        const ratio = dim.ratio ?? 0;
        return { key, label, ratio, score: dim.score, weight: dim.weight };
      }).filter(Boolean);

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <ClickableScoreTag
          type="current"
          score={evaluation.match_score}
          version={version}
          color="volcano"
          style={{ fontSize: 15, padding: '4px 10px' }}
        />
        {evaluation.potential_score != null && (
          <ClickableScoreTag
            type="potential"
            score={evaluation.potential_score}
            color="blue"
            style={{ fontSize: 15, padding: '4px 10px' }}
          />
        )}
        {evaluation.improvement_delta > 0 && (
          <Tag color="green" style={{ fontSize: 15, padding: '4px 10px' }}>
            可提升 +{evaluation.improvement_delta}
          </Tag>
        )}
        {tierTag(evaluation.match_tier)}
      </Space>

      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {displayReason}
      </Paragraph>

      <Divider orientation="left" plain>十维评分</Divider>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
        {dimensions.map(({ key, label, ratio, score, weight }) => (
          <div key={key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <Text>{label}</Text>
              <Text type="secondary">{score} / {(rawBreakdown?.[key]?.weight || weight || 0).toFixed(1)}</Text>
            </div>
            <Progress
              percent={Math.round(ratio * 100)}
              strokeColor={scoreColor(ratio)}
              size="small"
              showInfo={false}
            />
          </div>
        ))}
      </div>

      <Divider orientation="left" plain>技能差距</Divider>
      <Space wrap>
        {(apiBreakdown?.missing_skills || rawBreakdown?.skills?.missing || []).length > 0
          ? (apiBreakdown?.missing_skills || rawBreakdown?.skills?.missing || []).map((sk) => (
              <Tag key={sk} color="red">缺 {sk}</Tag>
            ))
          : <Text type="secondary">暂无</Text>}
        {(apiBreakdown?.matched_skills || rawBreakdown?.skills?.matched || []).map((sk) => (
          <Tag key={sk} color="green">✓ {sk}</Tag>
        ))}
      </Space>

      <Divider orientation="left" plain>软实力差距</Divider>
      <Space wrap>
        {filterSoftSkillsForDisplay(
          apiBreakdown?.soft_skills_missing || rawBreakdown?.soft_skills?.missing || [],
        ).length > 0
          ? filterSoftSkillsForDisplay(
              apiBreakdown?.soft_skills_missing || rawBreakdown?.soft_skills?.missing || [],
            ).map((sk) => (
              <Tag key={sk} color="orange">{sk}</Tag>
            ))
          : <Text type="secondary">暂无</Text>}
      </Space>

      {signals && (
        <>
          <Divider orientation="left" plain>补充信号</Divider>
          <Space wrap>
            {signals.stability && (
              <Tag>稳定性 {Math.round((signals.stability.ratio || 0) * 100)}%</Tag>
            )}
            {signals.probabilities && (
              <>
                <Tag color="processing">
                  面试概率 ~{signals.probabilities.interview_probability}%
                </Tag>
                <Tag color="purple">
                  Offer 概率 ~{signals.probabilities.offer_probability}%
                </Tag>
              </>
            )}
            {signals.upskill_difficulty?.level && (
              <Tag>补齐难度：{signals.upskill_difficulty.level}</Tag>
            )}
          </Space>
        </>
      )}

      {cs && (
        <>
          <Divider orientation="left" plain>
            <BulbOutlined /> 改进建议
          </Divider>
          <Alert type="success" message={cs.summary} style={{ marginBottom: 12 }} showIcon />

          {cs.experience_suggestions?.length > 0 && (
            <>
              <Text strong><BankOutlined /> 建议补充的经历</Text>
              <List
                size="small"
                style={{ marginTop: 8, marginBottom: 12 }}
                dataSource={cs.experience_suggestions}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          {item.title}
                          {item.estimated_score_gain && (
                            <Tag color="green">+{item.estimated_score_gain} 分</Tag>
                          )}
                        </Space>
                      }
                      description={
                        <>
                          <div>{item.why}</div>
                          {item.position_examples && (
                            <Text type="secondary">职位示例：{item.position_examples.join('、')}</Text>
                          )}
                          {item.company_examples && (
                            <div><Text type="secondary">公司示例：{item.company_examples.join('、')}</Text></div>
                          )}
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            </>
          )}

          {cs.project_suggestions?.length > 0 && (
            <>
              <Text strong><ProjectOutlined /> 建议做的项目</Text>
              <List
                size="small"
                style={{ marginTop: 8, marginBottom: 12 }}
                dataSource={cs.project_suggestions}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          {item.title}
                          {item.estimated_score_gain && (
                            <Tag color="green">+{item.estimated_score_gain} 分</Tag>
                          )}
                        </Space>
                      }
                      description={
                        <>
                          <div>{item.description}</div>
                          {item.deliverable && (
                            <Text type="secondary">交付物：{item.deliverable}</Text>
                          )}
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
            </>
          )}

          {cs.skill_projects?.length > 0 && (
            <>
              <Text strong><RocketOutlined /> 针对缺失技能的小项目</Text>
              <List
                size="small"
                style={{ marginTop: 8 }}
                dataSource={cs.skill_projects}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={`${item.skill} → ${item.title}`}
                      description={item.description}
                    />
                  </List.Item>
                )}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

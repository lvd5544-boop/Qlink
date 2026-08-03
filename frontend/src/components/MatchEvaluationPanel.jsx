import { Tag, Space, Typography, Divider, List, Alert } from 'antd';
import {
  RocketOutlined,
  BulbOutlined,
  ProjectOutlined,
  BankOutlined,
} from '@ant-design/icons';
import { resolveMatchBreakdown, filterSoftSkillsForDisplay } from '../utils/matchBreakdown';

const { Text } = Typography;

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

function factorTag(ratio) {
  if (ratio >= 0.8) return { text: '符合', color: 'success' };
  if (ratio >= 0.5) return { text: '基本符合', color: 'warning' };
  return { text: '需要确认', color: 'default' };
}

export default function MatchEvaluationPanel({ evaluation }) {
  if (!evaluation) {
    return <Alert type="info" message="暂无评分数据，请确认已上传简历" showIcon />;
  }

  const { breakdown: rawBreakdown, career_suggestions: cs } = evaluation;
  const apiBreakdown = evaluation.api_breakdown || resolveMatchBreakdown({
    breakdown: evaluation.api_breakdown,
    score_breakdown: rawBreakdown,
  });
  const dimensions = apiBreakdown?.dimensions?.length
    ? apiBreakdown.dimensions.map((d) => ({
        key: d.key,
        label: d.label,
        ratio: d.ratio ?? 0,
      }))
    : Object.entries(DIMENSION_LABELS).map(([key, label]) => {
        const dim = rawBreakdown?.[key];
        if (!dim) return null;
        const ratio = dim.ratio ?? 0;
        return { key, label, ratio };
      }).filter(Boolean);

  return (
    <div>
      <Divider orientation="left" plain>系统参考了什么</Divider>
      <Space wrap>
        {dimensions.map(({ key, label, ratio }) => {
          const status = factorTag(ratio);
          return <Tag key={key} color={status.color}>{label}：{status.text}</Tag>;
        })}
      </Space>

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

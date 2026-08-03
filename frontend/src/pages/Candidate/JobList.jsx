import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Card, Collapse, Descriptions, Form, Input, List, Modal, Select, Space, Spin,
  Tag, Typography, Button, message,
} from 'antd';
import {
  DollarOutlined, EnvironmentOutlined, ReloadOutlined, SettingOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../../api';
import MatchEvaluationPanel from '../../components/MatchEvaluationPanel';
import {
  resolveMatchBreakdown,
  resolveMatchReason,
  resolveMissingSkills,
} from '../../utils/matchBreakdown';

const { Text, Paragraph } = Typography;
const INDUSTRY_OPTIONS = [
  ['technology', '科技/软件'],
  ['finance', '金融'],
  ['healthcare', '医疗健康'],
  ['education_research', '教育/研究'],
  ['climate_energy', '环境/能源'],
  ['government_public', '政府/公共服务'],
  ['consumer_media', '消费/媒体/游戏'],
  ['manufacturing', '制造业'],
].map(([value, label]) => ({ value, label }));
const INDUSTRY_LABELS = Object.fromEntries(INDUSTRY_OPTIONS.map((item) => [item.value, item.label]));

function matchLabel(score) {
  if (Number(score) >= 8) return { text: '优先考虑', color: 'green' };
  if (Number(score) >= 6.5) return { text: '值得申请', color: 'blue' };
  return { text: '可以了解', color: 'default' };
}

function userFacingMatch(item, breakdown) {
  const policy = item.score_breakdown?.preference_policy || {};
  const genericSkills = new Set(['data', 'it', 'people', 'operations', 'engineering', 'development']);
  const missing = resolveMissingSkills(item, breakdown)
    .map((skill) => String(skill).replace(/^\d+\s+/, '').trim())
    .filter((skill) => skill && !genericSkills.has(skill.toLowerCase()))
    .slice(0, 3);
  const industries = (policy.industry_overlap || [])
    .map((key) => INDUSTRY_LABELS[key] || key);
  const strengths = [
    policy.role_relation === 'exact' ? '职业方向与你的目标一致' : '属于可以迁移的相邻方向',
    industries.length ? `行业经历可迁移：${industries.join('、')}` : null,
    (item.score_breakdown?.skills?.matched || []).length
      ? `已有相关技能：${item.score_breakdown.skills.matched.slice(0, 3).join('、')}`
      : null,
  ].filter(Boolean);
  const checks = [
    missing.length ? `申请前确认：${missing.join('、')}` : null,
    item.job_location ? `地点：${item.job_location}` : null,
  ].filter(Boolean);
  return { strengths, checks, missing };
}

function toEvaluation(item) {
  if (!item?.score_breakdown && !item?.breakdown) return null;
  const apiBreakdown = resolveMatchBreakdown(item);
  return {
    match_score: item.score,
    potential_score: item.potential_score ?? item.score_breakdown?.potential_score,
    improvement_delta: item.improvement_delta ?? item.score_breakdown?.improvement_delta ?? 0,
    match_tier: item.match_tier ?? item.score_breakdown?.match_tier,
    breakdown: item.score_breakdown,
    api_breakdown: apiBreakdown,
    reason: resolveMatchReason(item),
  };
}

export default function JobList() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [matchDetail, setMatchDetail] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [inferredIntent, setInferredIntent] = useState(null);
  const [visibleCount, setVisibleCount] = useState(8);
  const [preferencesForm] = Form.useForm();
  const hasAutoFetched = useRef(false);

  const userId = localStorage.getItem('user_id');

  const fetchMatches = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const params = isRefresh ? '?refresh=true' : '';
      const res = await api.get(`/matches/user/${userId}${params}`);
      setJobs(res.data);
      setVisibleCount(8);
      if (isRefresh) message.success('匹配已按职业方向与个人偏好更新');
    } catch {
      message.error('加载推荐岗位失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useEffect(() => {
    if (!hasAutoFetched.current) {
      hasAutoFetched.current = true;
      const timer = setTimeout(() => fetchMatches(true), 0);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [fetchMatches]);

  const openPreferences = async () => {
    try {
      const response = await api.get('/matching/preferences');
      const preferences = response.data?.preferences || {};
      preferencesForm.setFieldsValue({
        target_roles: (preferences.target_roles || []).join('、'),
        preferred_industries: preferences.preferred_industries || [],
        excluded_industries: preferences.excluded_industries || [],
        strictness: preferences.strictness || 'focused',
      });
      setInferredIntent(response.data?.inferred_intent || null);
      setPreferencesOpen(true);
    } catch {
      message.error('匹配偏好加载失败');
    }
  };

  const savePreferences = async (values) => {
    setPreferencesSaving(true);
    try {
      const targetRoles = String(values.target_roles || '')
        .split(/[、,，;；]/)
        .map((value) => value.trim())
        .filter(Boolean);
      const response = await api.put('/matching/preferences', {
        ...values,
        target_roles: targetRoles,
      });
      setInferredIntent(response.data?.inferred_intent || null);
      setPreferencesOpen(false);
      message.success('偏好已保存，正在按职业方向与行业重新筛选');
      window.setTimeout(() => fetchMatches(true), 1200);
    } catch {
      message.error('匹配偏好保存失败');
    } finally {
      setPreferencesSaving(false);
    }
  };

  const showJobDetail = async (jobId) => {
    setDetailLoading(true);
    try {
      const res = await api.get(`/job/${jobId}`);
      setSelectedJob(res.data);
    } catch {
      message.error('加载岗位详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const stopPropagation = (e) => e.stopPropagation();

  return (
    <Card
      className="content-card"
      title="推荐岗位"
      extra={
        <Space>
          <Button icon={<SettingOutlined />} onClick={openPreferences}>调整偏好</Button>
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => fetchMatches(true)}>
            刷新匹配
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="这里只展示符合你目标方向的岗位"
        description="先看推荐理由和需要确认的事项；评分方法放在详情里，需要时再查看。"
      />
      <Spin spinning={loading || refreshing}>
        <List
          dataSource={jobs.slice(0, visibleCount)}
          loadMore={visibleCount < jobs.length ? (
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Button onClick={() => setVisibleCount((count) => count + 8)}>
                查看更多岗位
              </Button>
            </div>
          ) : null}
          renderItem={(item) => {
            const breakdown = resolveMatchBreakdown(item);
            const summary = userFacingMatch(item, breakdown);
            const level = matchLabel(item.score);

            return (
              <List.Item
                className="job-list-item"
                style={{ cursor: 'pointer', alignItems: 'flex-start' }}
                onClick={() => setMatchDetail(item)}
                extra={
                  <div style={{ textAlign: 'right', minWidth: 150 }} onClick={stopPropagation}>
                    <Tag color={level.color} style={{ marginBottom: 8 }}>{level.text}</Tag>
                    <div style={{ color: '#64748b', fontSize: 13 }}>
                      <EnvironmentOutlined /> {item.job_location || '不限'}
                    </div>
                    <div style={{ color: '#64748b', fontSize: 13 }}>
                      <DollarOutlined /> {item.job_salary || '面议'}
                    </div>
                    <Button type="link" onClick={() => setMatchDetail(item)}>查看推荐理由</Button>
                  </div>
                }
              >
                <div style={{ flex: 1, minWidth: 0, paddingRight: 16 }}>
                  <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 6 }}>
                    {item.job_title}
                  </Text>
                  {item.score_breakdown?.preference_policy?.role_relation && (
                    <Tag
                      color={item.score_breakdown.preference_policy.role_relation === 'exact' ? 'green' : 'blue'}
                      style={{ marginBottom: 6 }}
                    >
                      {item.score_breakdown.preference_policy.role_relation === 'exact'
                        ? '职业方向一致'
                        : '相邻方向'}
                    </Tag>
                  )}
                  {summary.strengths.slice(0, 2).map((text) => (
                    <Paragraph key={text} type="secondary" style={{ marginBottom: 2, fontSize: 13 }}>
                      ✓ {text}
                    </Paragraph>
                  ))}
                  {summary.missing.length > 0 && (
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      申请前确认：{summary.missing.join('、')}
                    </Text>
                  )}
                </div>
              </List.Item>
            );
          }}
          locale={{ emptyText: '暂无匹配岗位，请先上传简历并确保有岗位可匹配' }}
        />
      </Spin>

      <Modal
        title={matchDetail?.job_title || '匹配详情'}
        open={!!matchDetail}
        onCancel={() => setMatchDetail(null)}
        footer={
          matchDetail ? (
            <Space>
              <Button onClick={() => showJobDetail(matchDetail.job_id)}>查看完整岗位</Button>
              <Button
                type="primary"
                onClick={() => navigate(`/candidate/advisor?job_id=${matchDetail.job_id}`)}
              >
                用这个岗位优化简历
              </Button>
            </Space>
          ) : null
        }
        width={780}
        destroyOnClose
      >
        {matchDetail && (() => {
          const breakdown = resolveMatchBreakdown(matchDetail);
          const summary = userFacingMatch(matchDetail, breakdown);
          const level = matchLabel(matchDetail.score);
          return (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Alert
                type={level.color === 'green' ? 'success' : 'info'}
                showIcon
                message={level.text}
                description="这是基于你的目标方向、经历和偏好给出的申请建议，不代表录用概率。"
              />
              <Card size="small" title="为什么推荐">
                <List
                  size="small"
                  dataSource={summary.strengths}
                  renderItem={(text) => <List.Item>✓ {text}</List.Item>}
                />
              </Card>
              <Card size="small" title="申请前需要确认">
                {summary.checks.length ? (
                  <List
                    size="small"
                    dataSource={summary.checks}
                    renderItem={(text) => <List.Item>{text}</List.Item>}
                  />
                ) : <Text type="secondary">暂时没有明显缺口，可以直接查看岗位详情。</Text>}
              </Card>
              <Collapse
                items={[{
                  key: 'calculation',
                  label: '查看系统判断依据（可选）',
                  children: <MatchEvaluationPanel evaluation={toEvaluation(matchDetail)} />,
                }]}
              />
            </Space>
          );
        })()}
      </Modal>

      <Modal
        title="岗位推荐偏好"
        open={preferencesOpen}
        onCancel={() => setPreferencesOpen(false)}
        footer={null}
        destroyOnClose
      >
        {inferredIntent && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`当前识别的主方向：${inferredIntent.role_label || '未识别'}`}
            description="这是根据你明确选择的目标岗位、简历意向、经历、项目和技能综合判断；填写目标岗位后以你的选择为先。"
          />
        )}
        <Form
          form={preferencesForm}
          layout="vertical"
          onFinish={savePreferences}
          initialValues={{ strictness: 'focused' }}
        >
          <Form.Item name="target_roles" label="目标岗位（最重要）">
            <Input placeholder="例如：数据科学家、机器学习工程师" />
          </Form.Item>
          <Form.Item name="preferred_industries" label="优先行业">
            <Select mode="multiple" allowClear options={INDUSTRY_OPTIONS} placeholder="不选则从经历推断，不做行业硬限制" />
          </Form.Item>
          <Form.Item name="excluded_industries" label="明确排除的行业">
            <Select mode="multiple" allowClear options={INDUSTRY_OPTIONS} />
          </Form.Item>
          <Form.Item name="strictness" label="推荐范围">
            <Select options={[
              { value: 'focused', label: '精准：只看目标职业方向' },
              { value: 'balanced', label: '均衡：允许相邻方向与跨行业' },
              { value: 'explore', label: '探索：展示跨方向机会并明确标注' },
            ]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={preferencesSaving} block>
            保存并重新匹配
          </Button>
        </Form>
      </Modal>

      <Modal
        title={selectedJob?.title}
        open={!!selectedJob}
        onCancel={() => setSelectedJob(null)}
        footer={null}
        width={700}
        destroyOnClose
      >
        <Spin spinning={detailLoading}>
          {selectedJob?.parsed && (
            <Descriptions bordered column={2}>
              {selectedJob.company_name && (
                <Descriptions.Item label="发布单位">{selectedJob.company_name}</Descriptions.Item>
              )}
              <Descriptions.Item label="工作地点">
                {selectedJob.parsed.location || '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="薪资范围">
                {selectedJob.parsed.salary_range || '面议'}
              </Descriptions.Item>
              <Descriptions.Item label="经验要求">
                {selectedJob.parsed.experience_years ? `${selectedJob.parsed.experience_years} 年` : '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="学历要求" span={2}>
                {selectedJob.parsed.education || '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="技能要求" span={2}>
                <Space wrap>
                  {(selectedJob.parsed.required_skills || []).map((skill, idx) => (
                    <Tag color="green" key={idx}>{skill.name}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="岗位职责" span={2}>
                <div style={{ maxHeight: 300, overflow: 'auto', lineHeight: 1.8 }}>
                  {Array.isArray(selectedJob.parsed.responsibilities)
                    ? selectedJob.parsed.responsibilities.join('\n')
                    : selectedJob.parsed.responsibilities || ''}
                </div>
              </Descriptions.Item>
            </Descriptions>
          )}
        </Spin>
      </Modal>
    </Card>
  );
}

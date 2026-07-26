import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, List, Tag, message, Spin, Button, Modal, Descriptions, Space, Typography } from 'antd';
import { ReloadOutlined, EnvironmentOutlined, DollarOutlined, RobotOutlined } from '@ant-design/icons';
import api from '../../api';
import MatchEvaluationPanel from '../../components/MatchEvaluationPanel';
import MatchBreakdownPreview from '../../components/MatchBreakdownPreview';
import { ClickableScoreTag } from '../../components/ScoreRulesPopover';
import { resolveMatchBreakdown, resolveMatchReason } from '../../utils/matchBreakdown';

const { Text, Paragraph } = Typography;

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
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [matchDetail, setMatchDetail] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const hasAutoFetched = useRef(false);

  const userId = localStorage.getItem('user_id');

  const fetchMatches = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const params = isRefresh ? '?refresh=true' : '';
      const res = await api.get(`/matches/user/${userId}${params}`);
      setJobs(res.data);
      if (isRefresh) message.success('匹配已更新（hybrid + Top5 LLM 重排）');
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
        <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => fetchMatches(true)}>
          刷新匹配
        </Button>
      }
    >
      <Spin spinning={loading || refreshing}>
        <List
          dataSource={jobs}
          renderItem={(item) => {
            const breakdown = resolveMatchBreakdown(item);
            const displayReason = resolveMatchReason(item);
            const version = breakdown?.version ?? item.score_breakdown?.version ?? 2;

            return (
              <List.Item
                className="job-list-item"
                style={{ cursor: 'pointer', alignItems: 'flex-start' }}
                onClick={() => setMatchDetail(item)}
                extra={
                  <div style={{ textAlign: 'right', minWidth: 120 }} onClick={stopPropagation}>
                    <ClickableScoreTag
                      type="current"
                      score={item.score}
                      version={version}
                      color="volcano"
                      style={{ fontSize: 16 }}
                    />
                    {item.potential_score != null && (
                      <div style={{ marginTop: 4 }}>
                        <ClickableScoreTag
                          type="potential"
                          score={item.potential_score}
                          color="blue"
                        />
                      </div>
                    )}
                    {item.llm_reranked && (
                      <div style={{ marginTop: 4 }}>
                        <Tag icon={<RobotOutlined />} color="purple">AI 解读</Tag>
                      </div>
                    )}
                    <div style={{ marginTop: 8, color: '#64748b', fontSize: 13 }}>
                      <EnvironmentOutlined /> {item.job_location || '不限'}
                    </div>
                    <div style={{ color: '#64748b', fontSize: 13 }}>
                      <DollarOutlined /> {item.job_salary || '面议'}
                    </div>
                  </div>
                }
              >
                <div style={{ flex: 1, minWidth: 0, paddingRight: 16 }}>
                  <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 6 }}>
                    {item.job_title}
                  </Text>
                  {item.score_breakdown?.role_match?.family_mismatch && (
                    <Tag color="red" style={{ marginBottom: 6 }}>职位方向不符</Tag>
                  )}
                  <Paragraph
                    type="secondary"
                    style={{ marginBottom: 0, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}
                  >
                    {displayReason}
                  </Paragraph>
                  <MatchBreakdownPreview item={item} breakdown={breakdown} compact />
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
            <Button onClick={() => showJobDetail(matchDetail.job_id)}>查看岗位 JD</Button>
          ) : null
        }
        width={780}
        destroyOnClose
      >
        <MatchEvaluationPanel evaluation={toEvaluation(matchDetail)} />
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

import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Button, Card, Col, Divider, List, Modal, Progress, Row, Select, Space, Spin, Tag, Typography, message,
} from 'antd';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';
import { decodeHtmlEntities } from '../utils/text';
import PersonalizedGuidancePanel from './PersonalizedGuidancePanel';
import OpportunityPreparationCard from './OpportunityPreparationCard';

const { Paragraph, Text } = Typography;

const severity = {
  blocker: { label: '阻断问题', color: 'red' },
  high: { label: '高影响问题', color: 'volcano' },
  medium: { label: '增强问题', color: 'gold' },
  low: { label: '可选优化', color: 'blue' },
};

const categoryLabel = {
  expression: '表达',
  evidence: '证据',
  capability: '能力',
  hard_constraint: '硬门槛',
  consistency: '一致性',
  structure_ats: '结构与 ATS',
  relevance: '岗位相关性',
  differentiation: '差异化',
  career_narrative: '职业叙事',
  privacy_compliance: '隐私与合规',
};

const horizonLabel = {
  immediate: '现在就可以开始',
  short_term: '预计 1–2 周',
  medium_term: '预计 4–8 周',
  long_term: '预计 3 个月以上',
};

const costLabel = {
  low: '投入较少，通常 1 小时内可完成',
  medium: '需要持续投入，建议每周安排 3–5 小时',
  high: '投入较大，建议拆成多个阶段完成',
};

const idem = (scope) => ({ headers: { 'Idempotency-Key': `${scope}:${Date.now()}:${Math.random().toString(36).slice(2)}` } });

export default function TargetJobOptimizationPanel({
  resumeId,
  targetJobId = null,
  onTargetJobChange,
  onApplied,
  onFocusClaims,
}) {
  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState(null);
  const [diagnostic, setDiagnostic] = useState(null);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [proposal, setProposal] = useState(null);
  const [action, setAction] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    api.get('/browse-jobs').then((response) => {
      if (!active) return;
      const rows = Array.isArray(response.data) ? response.data : (response.data?.jobs || []);
      if (!targetJobId || rows.some((item) => String(item.id) === String(targetJobId))) {
        setJobs(rows);
        return;
      }
      api.get(`/advisor/jobs/${targetJobId}/profile`).then((profileResponse) => {
        if (!active) return;
        const privateJob = profileResponse.data?.job;
        setJobs(privateJob?.id ? [privateJob, ...rows] : rows);
      }).catch(() => {
        if (active) setJobs(rows);
      });
    }).catch(() => {
      if (active) setJobs([]);
    });
    return () => { active = false; };
  }, [targetJobId]);

  const effectiveJobId = targetJobId || jobId;

  const changeJob = (value) => {
    setJobId(value);
    setDiagnostic(null);
    setSelectedIssue(null);
    setProposal(null);
    setAction(null);
    onTargetJobChange?.(jobs.find((job) => String(job.id) === String(value)) || { id: value });
  };

  const generate = async () => {
    if (!effectiveJobId) {
      message.warning('请先选择目标岗位');
      return;
    }
    setLoading(true);
    try {
      const response = await api.post(
        `/resumes/${resumeId}/jobs/${effectiveJobId}/diagnostics`,
        {},
        idem('pr13-diagnostic'),
      );
      setDiagnostic(response.data);
      setSelectedIssue(response.data.issues?.[0] || null);
      setProposal(null);
      message.success(`已生成 ${response.data.issues?.length || 0} 个岗位定制诊断问题`);
    } catch (error) {
      message.error(getApiErrorMessage(error, '生成岗位诊断失败'));
    } finally {
      setLoading(false);
    }
  };

  const chooseStrategy = async (issue, strategy) => {
    setLoading(true);
    try {
      const response = await api.post(
        `/optimization/issues/${issue.id}/select-strategy`,
        { strategy_id: strategy.id },
        idem(`pr13-strategy-${issue.id}`),
      );
      setAction(response.data.action);
      setSelectedIssue(issue);
      message.success('策略已加入行动路径');
    } catch (error) {
      message.error(getApiErrorMessage(error, '选择策略失败'));
    } finally {
      setLoading(false);
    }
  };

  const preview = async (issue, strategy) => {
    setLoading(true);
    try {
      const response = await api.post(
        `/optimization/issues/${issue.id}/rewrite-preview`,
        { strategy_id: strategy.id },
        idem(`pr13-preview-${issue.id}`),
      );
      setSelectedIssue(issue);
      setProposal(response.data);
    } catch (error) {
      message.error(getApiErrorMessage(error, '当前事实不足，不能生成忠实改写'));
    } finally {
      setLoading(false);
    }
  };

  const locateAndPreview = async (issue) => {
    onFocusClaims?.(issue);
    const strategy = (issue.strategies || []).find((item) => item.recommended)
      || issue.strategies?.[0];
    if (strategy) {
      await preview(issue, strategy);
      document.getElementById('target-job-optimization')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }
  };

  const reject = async () => {
    if (!proposal) return;
    await api.post(`/resume-patches/${proposal.id}/reject`, {}, idem(`pr13-reject-${proposal.id}`));
    setProposal((old) => ({ ...old, status: 'rejected' }));
    message.info('已拒绝该改写，不会修改简历');
  };

  const confirmAndApply = async () => {
    if (!proposal) return;
    setLoading(true);
    try {
      await api.post(
        `/resume-patches/${proposal.id}/confirm-facts`,
        {},
        idem(`pr13-confirm-${proposal.id}`),
      );
      const response = await api.post(
        `/resume-patches/${proposal.id}/apply`,
        {},
        idem(`pr13-apply-${proposal.id}`),
      );
      setProposal(response.data);
      message.success(`已创建简历版本 v${response.data.resume_version.version_number}，历史版本保持不变`);
      onApplied?.(response.data);
    } catch (error) {
      message.error(getApiErrorMessage(error, '事实核对没有通过，请检查改写中是否出现了简历里没有的信息'));
    } finally {
      setLoading(false);
    }
  };

  const groupedCounts = useMemo(() => (
    Object.entries(diagnostic?.categories || {})
      .filter(([, rows]) => rows.length)
      .map(([key, rows]) => `${categoryLabel[key] || key} ${rows.length}`)
  ), [diagnostic]);

  return (
    <Card id="target-job-optimization" title="围绕目标岗位优化简历" style={{ marginTop: 16 }}>
      <Alert
        showIcon
        type="info"
        message="先选定一份真实岗位。诊断和改写只使用你已经提供的经历与证据，不会把岗位要求写成你的经历。"
        style={{ marginBottom: 12 }}
      />
      <Spin spinning={loading}>
        <Row gutter={[12, 12]}>
          <Col xs={24} xl={6}>
            <Card size="small" title="① 选择目标岗位">
              <Select
                data-testid="pr13-target-job-select"
                showSearch
                allowClear
                value={effectiveJobId}
                onChange={changeJob}
                placeholder="必须先选择岗位"
                style={{ width: '100%' }}
                options={jobs.map((job) => ({
                  value: job.id,
                  label: `${decodeHtmlEntities(job.title) || job.id}${job.company_name ? ` · ${decodeHtmlEntities(job.company_name)}` : ''}`,
                }))}
                optionFilterProp="label"
              />
              <Button
                data-testid="pr13-generate-diagnostic"
                type="primary"
                block
                style={{ marginTop: 10 }}
                disabled={!effectiveJobId}
                onClick={generate}
              >
                分析我与这个岗位的差距
              </Button>
              {!effectiveJobId && <Text type="secondary">请先从上方选择一份岗位。</Text>}
              {diagnostic && (
                <>
                  <Divider />
                  <Text strong>问题总览</Text>
                  <div style={{ marginTop: 8 }}>
                    {groupedCounts.map((item) => <Tag key={item}>{item}</Tag>)}
                  </div>
                </>
              )}
            </Card>
          </Col>

          <Col xs={24} xl={6}>
            <Card size="small" title="② 多问题诊断">
              {!diagnostic ? <Text type="secondary">选择岗位并生成诊断后显示。</Text> : (
                <List
                  size="small"
                  dataSource={diagnostic.issues}
                  renderItem={(issue) => (
                    <List.Item onClick={() => setSelectedIssue(issue)} style={{ cursor: 'pointer' }}>
                      <div>
                        <Space wrap>
                          <Tag color={severity[issue.severity]?.color}>{severity[issue.severity]?.label}</Tag>
                          <Tag>{categoryLabel[issue.category] || issue.category}</Tag>
                        </Space>
                        <Paragraph style={{ margin: '6px 0 0' }}>{issue.diagnosis}</Paragraph>
                        {issue.claim_ids?.length > 0 && (
                          <Button
                            type="link"
                            size="small"
                            style={{ padding: 0 }}
                            onClick={(event) => {
                              event.stopPropagation();
                              locateAndPreview(issue);
                            }}
                          >
                            定位相关经历并生成改写
                          </Button>
                        )}
                      </div>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>

          <Col xs={24} xl={6}>
            <Card size="small" title="③ 选择改进方式并预览">
              {!selectedIssue ? <Text type="secondary">请选择一个问题。</Text> : (
                <>
                  <Paragraph>{selectedIssue.diagnosis}</Paragraph>
                  {(selectedIssue.strategies || []).map((strategy) => (
                    <Card key={strategy.id} size="small" style={{ marginBottom: 8 }}>
                      <Text strong>{strategy.title}</Text>
                      {strategy.recommended && <Tag color="blue" style={{ marginLeft: 6 }}>推荐</Tag>}
                      <Paragraph type="secondary">{strategy.why}</Paragraph>
                      <Space wrap>
                        <Button size="small" onClick={() => chooseStrategy(selectedIssue, strategy)}>加入我的计划</Button>
                        <Button
                          data-testid={`pr13-preview-${strategy.strategy}`}
                          size="small"
                          type="primary"
                          disabled={!selectedIssue.claim_ids?.length}
                          onClick={() => preview(selectedIssue, strategy)}
                        >
                          查看改写前后对照
                        </Button>
                      </Space>
                    </Card>
                  ))}
                  {proposal && (
                    <Card size="small" title="改写前后对照">
                      <Text type="secondary">{proposal.observation}</Text>
                      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>原文</Text>
                      <Paragraph>{proposal.before_text || '（原文为空）'}</Paragraph>
                      <Text type="secondary" style={{ display: 'block' }}>建议写法</Text>
                      <Paragraph mark>{proposal.after_text}</Paragraph>
                      <div>依据：你的履历记录 {proposal.source_claim_ids.map((id) => <Tag key={id}>{id.slice(0, 8)}</Tag>)}</div>
                      <Tag color={proposal.fidelity_status === 'ready' ? 'green' : 'red'}>
                        {proposal.fidelity_status === 'ready' ? '事实核对通过' : '需要补充事实'}
                      </Tag>
                      <Space style={{ marginTop: 8 }}>
                        <Button danger onClick={reject}>拒绝</Button>
                        <Button
                          data-testid="pr13-confirm-and-apply"
                          type="primary"
                          disabled={proposal.status === 'applied' || proposal.status === 'rejected'}
                          onClick={() => Modal.confirm({
                            title: '逐条确认这些事实来自你的材料？',
                            content: '保存前系统会重新读取你的履历记录，并再次检查改写中有没有新增未经支持的事实。',
                            onOk: confirmAndApply,
                          })}
                        >
                          确认无误并保存为新版本
                        </Button>
                      </Space>
                    </Card>
                  )}
                </>
              )}
            </Card>
          </Col>

          <Col xs={24} xl={6}>
            <Card size="small" title="④ 当前差距与下一步">
              {!diagnostic ? <Text type="secondary">暂无岗位准备度。</Text> : (
                <>
                  <Text>当前准备度</Text>
                  <Progress percent={Number(diagnostic.readiness.current || 0)} />
                  <Text>完成计划后的参考情景（暂不计入当前分数）</Text>
                  <Progress
                    status="normal"
                    strokeColor="#94a3b8"
                    percent={Number(diagnostic.readiness.future_scenario || 0)}
                  />
                  <Alert type="warning" showIcon message={diagnostic.readiness.notice} />
                  <Divider />
                  <PersonalizedGuidancePanel
                    guidance={diagnostic.personalized_guidance}
                    fallback={diagnostic.decision_trace.recommended_next_actions || []}
                  />
                  {action && (
                    <Alert
                      type="success"
                      showIcon
                      message={`已规划：${action.title}`}
                      description={(
                        <>
                          <Paragraph style={{ marginBottom: 6 }}>{action.description}</Paragraph>
                          <div>{horizonLabel[action.expected_time_horizon] || '完成时间需要自行安排'}</div>
                          <div>{costLabel[action.user_cost] || '请根据实际情况安排投入'}</div>
                          <div style={{ marginTop: 6 }}>
                            完成标准：形成一项可展示的真实产出，并把过程、个人贡献和结果补充到履历记录后重新诊断。
                          </div>
                        </>
                      )}
                    />
                  )}
                </>
              )}
            </Card>
          </Col>
        </Row>
        {diagnostic && (
          <OpportunityPreparationCard
            resumeId={resumeId}
            jobId={effectiveJobId}
            diagnostic={diagnostic}
          />
        )}
      </Spin>
    </Card>
  );
}

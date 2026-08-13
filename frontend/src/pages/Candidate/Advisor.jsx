import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  List,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ApartmentOutlined,
  AuditOutlined,
  DatabaseOutlined,
  CompassOutlined,
  FileAddOutlined,
  FundOutlined,
  LinkOutlined,
  RobotOutlined,
  SendOutlined,
  SolutionOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import { createIdempotencyTracker } from '../../utils/idempotency';
import CandidateActionMap from '../../components/CandidateActionMap';
import { replaceHypothesisStatus } from '../../components/hypothesisReview';
import PersonalizedGuidancePanel from '../../components/PersonalizedGuidancePanel';
import { isEnglishDemoMode } from '../../utils/demoMode';

const { Paragraph, Text, Title } = Typography;

const LAYER_META = {
  target_role: {
    icon: <SolutionOutlined />,
    kicker: 'A · 企业岗位真相源',
    color: '#3458d4',
    provenance: '来源：当前岗位 JD 与企业在本平台确认的岗位要求。',
  },
  occupation: {
    icon: <CompassOutlined />,
    kicker: 'B · 职业通用参考',
    color: '#7057c7',
    provenance: '来源：中国职业分类固定术语索引；只做职业归一化，不代表企业要求。',
  },
  company_context: {
    icon: <ApartmentOutlined />,
    kicker: 'C · 公司公开语境',
    color: '#137f77',
    provenance: '候选来源：该公司官网、年报、投资者关系页面和官方技术资料。只有登记许可、版本和有效期后才展示。',
  },
  market_signal: {
    icon: <FundOutlined />,
    kicker: 'D · 经许可市场信号',
    color: '#b26a16',
    provenance: '候选来源：取得许可并完成去标识化的公开 JD 聚合、政府职业统计或合作数据集；不会使用论坛传闻作正式结论。',
  },
};

function SourceChips({ citations = [] }) {
  if (!citations.length) return null;
  return (
    <Space wrap size={[4, 4]}>
      {citations.map((citation) => (
        <Tag icon={<LinkOutlined />} key={`${citation.source_id}:${citation.source_version_id}`}>
          {citation.source_name}
          {citation.source_version_id ? ` · v${citation.source_version_id.slice(0, 8)}` : ''}
          {citation.effective_at ? ` · ${new Date(citation.effective_at).toLocaleDateString()}` : ''}
        </Tag>
      ))}
    </Space>
  );
}

function ProfileLayer({ type, layer }) {
  const meta = LAYER_META[type];
  const requirements = layer?.requirements || [];
  const facts = layer?.facts || [];
  const occupationItems = [
    ...(layer?.occupations || []),
    ...(layer?.adjacent_skills || []),
    ...(layer?.work_themes || []),
  ];
  const items = requirements.length
    ? requirements.map((item) => ({
      key: item.id,
      title: item.text,
      detail: `${item.type} · ${item.level}${item.employer_confirmed ? ' · 企业已确认' : ''}`,
      citations: item.citations,
    }))
    : [...facts, ...occupationItems].map((item, index) => ({
      key: `${type}-${index}`,
      title: item,
      citations: layer?.citations,
    }));

  return (
    <Card className={`advisor-layer advisor-layer-${type}`} bordered={false}>
      <Space align="start" size={12}>
        <Avatar
          shape="square"
          size={42}
          icon={meta.icon}
          style={{ background: meta.color }}
        />
        <div>
          <Text type="secondary" className="advisor-layer-kicker">{meta.kicker}</Text>
          <Title level={4} style={{ margin: '2px 0 4px' }}>{layer?.title}</Title>
          <Text type="secondary">{layer?.caveat}</Text>
          <Paragraph type="secondary" style={{ margin: '6px 0 0', fontSize: 12 }}>
            {meta.provenance}
          </Paragraph>
        </div>
      </Space>
      <div className="advisor-layer-content">
        {items.length ? (
          <List
            size="small"
            dataSource={items}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={3}>
                  <Paragraph
                    ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                    style={{ marginBottom: 0 }}
                  >
                    {item.title}
                  </Paragraph>
                  {item.detail && <Text type="secondary">{item.detail}</Text>}
                  <SourceChips citations={item.citations} />
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <div className="advisor-layer-empty">
            <DatabaseOutlined />
            <div>
              <Text strong>来源尚未达到正式展示门槛</Text>
              <Paragraph type="secondary" style={{ margin: '4px 0 8px' }}>
                {layer?.empty_reason || '当前没有可用信息'}
              </Paragraph>
              {layer?.next_step && <Text>{layer.next_step}</Text>}
              <Paragraph type="secondary" style={{ margin: '8px 0 0', fontSize: 12 }}>
                “0”表示当前岗位快照中没有已批准且未过期的来源版本，不代表系统抓取失败，也不会用未知来源自动补齐。
              </Paragraph>
            </div>
            {layer?.source_status && (
              <Tag>
                已审核来源 {layer.source_status.approved_sources || 0}
              </Tag>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function AdvisorAnswer({ item }) {
  if (item.role === 'user') {
    return (
      <div className="advisor-message advisor-message-user">
        <Text>{item.content}</Text>
      </div>
    );
  }
  return (
    <div className="advisor-message advisor-message-ai">
      <Space align="start">
        <Avatar icon={<RobotOutlined />} style={{ background: '#3458d4' }} />
        <div style={{ flex: 1 }}>
          {(item.statements || []).map((statement, index) => (
            <Card size="small" className="advisor-statement" key={`${item.id}-${index}`}>
              <Paragraph style={{ margin: 0 }}>{statement.text}</Paragraph>
              {(statement.citations || []).length > 0 && (
                <Collapse
                  ghost
                  size="small"
                  items={[{
                    key: 'sources',
                    label: '查看信息来源',
                    children: <SourceChips citations={statement.citations} />,
                  }]}
                />
              )}
            </Card>
          ))}
          {item.response_trace && (
            <Collapse
              ghost
              size="small"
              items={[{
                key: 'trace',
                label: '查看回答限制与技术记录（可选）',
                children: (
                  <Space direction="vertical">
                    <Text type="secondary">
                      快照：{item.response_trace.snapshot_hash?.slice(0, 16) || '—'}
                    </Text>
                    {(item.response_trace.uncertainties || []).map((text) => (
                      <Text type="secondary" key={text}>不确定性：{text}</Text>
                    ))}
                    {(item.response_trace.alternative_explanations || []).map((text) => (
                      <Text type="secondary" key={text}>替代解释：{text}</Text>
                    ))}
                  </Space>
                ),
              }]}
            />
          )}
        </div>
      </Space>
    </div>
  );
}

export default function Advisor() {
  const englishDemo = isEnglishDemoMode();
  const navigate = useNavigate();
  const diagnosticIdempotency = useRef(createIdempotencyTracker('advisor-diagnostic'));
  const targetImportIdempotency = useRef(createIdempotencyTracker('advisor-target-import'));
  const [searchParams, setSearchParams] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [profile, setProfile] = useState(null);
  const [messages, setMessages] = useState([]);
  const [selectedResumeId, setSelectedResumeId] = useState();
  const [input, setInput] = useState('');
  const [diagnostic, setDiagnostic] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [importOpen, setImportOpen] = useState(() => searchParams.get('import') === '1');
  const [importTitle, setImportTitle] = useState('');
  const [importJd, setImportJd] = useState('');
  const [importing, setImporting] = useState(false);
  const [recordingApplication, setRecordingApplication] = useState(false);
  const jobId = searchParams.get('job_id') || '';

  const jobOptions = useMemo(
    () => jobs.map((job) => ({
      value: job.id,
      label: englishDemo && /[\u3400-\u9FFF]/.test(job.title || '')
        ? 'Example Target Role'
        : `${job.title}${job.company_name ? ` · ${job.company_name}` : ''}`,
    })),
    [englishDemo, jobs],
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get('/browse-jobs', { params: { sort_by: 'created_at' } }),
      api.get(`/resumes/${localStorage.getItem('user_id')}`),
    ]).then(([jobsRes, resumesRes]) => {
      if (cancelled) return;
      const nextJobs = jobsRes.data || [];
      const nextResumes = resumesRes.data || [];
      setJobs(nextJobs);
      setResumes(nextResumes);
      if (nextResumes.length) setSelectedResumeId(nextResumes[0].id);
      if (!jobId && nextJobs.length) {
        setSearchParams({ job_id: nextJobs[0].id }, { replace: true });
      }
    }).catch((error) => {
      if (!cancelled) message.error(getApiErrorMessage(error, '加载顾问数据失败'));
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, setSearchParams]);

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;
    Promise.all([
      api.get(`/advisor/jobs/${jobId}/profile`),
      api.get(`/advisor/jobs/${jobId}/chat/messages`),
    ]).then(([profileRes, chatRes]) => {
      if (cancelled) return;
      setProfile(profileRes.data);
      setMessages(chatRes.data?.messages || []);
      setDiagnostic(null);
      setLoading(false);
    }).catch((error) => {
      if (!cancelled) {
        setLoading(false);
        message.error(getApiErrorMessage(error, '加载岗位画像失败'));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const send = async () => {
    const text = input.trim();
    if (!text || !jobId) return;
    setSending(true);
    const optimistic = { id: `local-${Date.now()}`, role: 'user', content: text };
    setMessages((current) => [...current, optimistic]);
    setInput('');
    try {
      const response = await api.post(
        `/advisor/jobs/${jobId}/chat/messages`,
        { message: text, resume_id: selectedResumeId || null },
        { headers: { 'Idempotency-Key': `advisor-${jobId}-${Date.now()}` } },
      );
      setMessages((current) => [...current, response.data]);
    } catch (error) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setInput(text);
      message.error(getApiErrorMessage(error, '顾问暂时无法回答'));
    } finally {
      setSending(false);
    }
  };

  const importTargetJob = async () => {
    const descriptionText = importJd.trim();
    if (!descriptionText) {
      message.warning(englishDemo ? 'Paste the complete target-role JD' : '请粘贴完整的目标岗位 JD');
      return;
    }
    const requestPayload = {
      title: importTitle.trim() || null,
      description_text: descriptionText,
    };
    const idempotencyKey = targetImportIdempotency.current.keyFor(requestPayload);
    setImporting(true);
    try {
      const response = await api.post(
        '/advisor/target-jobs/import',
        requestPayload,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      targetImportIdempotency.current.complete(idempotencyKey);
      const importedJob = response.data?.job;
      if (!importedJob?.id) throw new Error('target_job_import_missing_id');
      setJobs((current) => [
        importedJob,
        ...current.filter((item) => String(item.id) !== String(importedJob.id)),
      ]);
      setProfile(response.data);
      setMessages([]);
      setDiagnostic(null);
      setImportOpen(false);
      setImportTitle('');
      setImportJd('');
      setLoading(true);
      setSearchParams({ job_id: importedJob.id });
      message.success(englishDemo ? 'Target JD imported. Review the requirements and reason about the next action.' : '目标 JD 已导入，现在可以核对岗位要求并分析下一步');
    } catch (error) {
      message.error(getApiErrorMessage(error, '目标 JD 导入失败，请检查内容后重试'));
    } finally {
      setImporting(false);
    }
  };

  const generateReadiness = async () => {
    if (!jobId || !selectedResumeId) {
      message.warning(englishDemo ? 'Select a resume first' : '请先选择一份简历');
      return;
    }
    setDiagnosing(true);
    const requestPayload = { resume_id: selectedResumeId };
    const idempotencyKey = diagnosticIdempotency.current.keyFor({
      job_id: jobId,
      ...requestPayload,
    });
    try {
      const response = await api.post(
        `/advisor/jobs/${jobId}/diagnostics`,
        requestPayload,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      diagnosticIdempotency.current.complete(idempotencyKey);
      setDiagnostic(response.data);
    } catch (error) {
      message.error(getApiErrorMessage(error, '生成岗位准备度失败'));
    } finally {
      setDiagnosing(false);
    }
  };
  const targetRequirements = profile?.layers?.target_role?.requirements || [];

  const openApplicationWorkbench = () => {
    if (!selectedResumeId || !jobId) return;
    const params = new URLSearchParams({ resumeId: selectedResumeId, jobId });
    navigate(`/candidate/my-resumes?${params.toString()}`);
  };

  const resolveIssueInResume = (issue) => {
    if (!selectedResumeId || !jobId) return;
    const params = new URLSearchParams({
      resumeId: selectedResumeId,
      jobId,
      claimHint: issue?.diagnosis || '请补充这条经历的背景、本人角色、行动、结果和证据。',
    });
    navigate(`/candidate/my-resumes?${params.toString()}`);
  };

  const updateHypothesis = async (hypothesis, status) => {
    try {
      const response = await api.post(
        `/optimization/hypotheses/${hypothesis.id}/status`,
        { status },
        { headers: { 'Idempotency-Key': `c5-hypothesis-${hypothesis.id}-${status}` } },
      );
      setDiagnostic((current) => replaceHypothesisStatus(current, hypothesis.id, response.data));
      message.success(status === 'rejected' ? '已排除这条可能性' : '已记录本人确认；尚未写入简历事实');
    } catch (error) {
      message.error(getApiErrorMessage(error, '更新假设状态失败'));
    }
  };

  const recordExternalApplication = async () => {
    if (!selectedResumeId || !jobId) return;
    setRecordingApplication(true);
    try {
      const response = await api.post('/applications/external-tracking', {
        job_id: jobId,
        resume_id: selectedResumeId,
      });
      const applicationId = response.data?.application?.id;
      message.success(response.data?.status === 'exists' ? '该站外投递已记录' : '已记录站外投递');
      navigate(`/candidate/applied-jobs${applicationId ? `?applicationId=${applicationId}` : ''}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, '记录站外投递失败'));
    } finally {
      setRecordingApplication(false);
    }
  };

  return (
    <div className="advisor-page">
      <Card className="content-card advisor-hero" bordered={false}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space>
            <Avatar size={48} icon={<AuditOutlined />} style={{ background: '#202c5d' }} />
            <div>
              <Title
                level={3}
                style={{ margin: 0, overflowWrap: 'anywhere' }}
              >
                {englishDemo ? 'Role Readiness Advisor' : '岗位准备助手'}
              </Title>
              <Text type="secondary">
                {englishDemo
                  ? 'AI reasons about the evidence gap, then designs the next question or task.'
                  : '选择岗位和简历，直接看你最该准备什么。'}
              </Text>
            </div>
          </Space>
          <Space wrap>
            <Select
              showSearch
              optionFilterProp="label"
              value={jobId || undefined}
              options={jobOptions}
              className="advisor-job-select"
              placeholder={englishDemo ? 'Select a target role' : '选择目标岗位'}
              onChange={(value) => setSearchParams({ job_id: value })}
            />
            <Button icon={<FileAddOutlined />} onClick={() => setImportOpen(true)}>
              {englishDemo ? 'Paste Target JD' : '粘贴目标 JD'}
            </Button>
            <Select
              allowClear
              value={selectedResumeId}
              className="advisor-resume-select"
              placeholder={englishDemo ? 'Select a resume to map your evidence' : '选择简历以核对你的材料'}
              onChange={setSelectedResumeId}
              options={resumes.map((resume, index) => ({
                value: resume.id,
                label: `${resume.parsed?.name || `${englishDemo ? 'Resume' : '简历'} ${index + 1}`} · ${resume.parsed?.expected_job_title || (englishDemo ? 'Direction not set' : '未填写方向')}`,
              }))}
            />
            <Button
              type="primary"
              loading={diagnosing}
              disabled={!jobId || !selectedResumeId}
              onClick={generateReadiness}
            >
              {englishDemo ? 'Reason About My Next Action' : '分析我该先做什么'}
            </Button>
          </Space>
          {profile?.snapshot?.is_stale && (
            <Alert
              showIcon
              type="warning"
              message={englishDemo ? 'Some sources have expired' : '部分来源已经过期'}
              description={englishDemo
                ? 'Expired sources will not be used for new answers.'
                : '顾问不会继续把过期来源用于新回答；请等待管理员发布新版本。'}
            />
          )}
        </Space>
      </Card>

      <Modal
        title={englishDemo ? 'Paste the role you actually want' : '粘贴你真正想申请的岗位'}
        open={importOpen}
        okText={englishDemo ? 'Import and Extract Requirements' : '导入并查看岗位要求'}
        cancelText={englishDemo ? 'Cancel' : '取消'}
        confirmLoading={importing}
        onOk={importTargetJob}
        onCancel={() => {
          if (!importing) setImportOpen(false);
        }}
        destroyOnHidden
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            showIcon
            type="info"
            message={englishDemo ? 'The JD defines the target—not your experience' : 'JD 只用于理解目标岗位'}
            description={englishDemo
              ? 'QLink never turns role requirements into claims about you. The imported role stays private.'
              : '系统不会把岗位要求当成你的经历，也不会把你导入的岗位公开到岗位列表。'}
          />
          <Input
            value={importTitle}
            maxLength={255}
            placeholder={englishDemo ? 'Role title (optional), e.g. AI Product Manager' : '岗位名称（可选，例如：AI 产品经理）'}
            onChange={(event) => setImportTitle(event.target.value)}
          />
          <Input.TextArea
            value={importJd}
            autoSize={{ minRows: 8, maxRows: 16 }}
            maxLength={100000}
            showCount
            placeholder={englishDemo ? 'Paste the complete JD from a company or recruiting platform' : '从企业官网、招聘平台或招聘方消息中粘贴完整 JD'}
            onChange={(event) => setImportJd(event.target.value)}
          />
          <Text type="secondary">
            {englishDemo
              ? 'QLink extracts the key requirements, maps your existing evidence, and identifies the next question or task.'
              : '导入后先查看系统提取的关键要求，再选择简历分析已有证据、信息缺口和下一步行动。'}
          </Text>
        </Space>
      </Modal>

      <Spin spinning={loading}>
        {profile ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Card className="content-card" title={englishDemo ? '5–8 Key Role Requirements' : '这个岗位最看重什么'}>
              {targetRequirements.length ? (
                <List
                  size="small"
                  dataSource={targetRequirements.slice(0, 6)}
                  renderItem={(item) => <List.Item>{item.text}</List.Item>}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={englishDemo ? 'The explicit role requirements are incomplete.' : '这个岗位的明确要求还不完整，可以先查看完整岗位说明'}
                />
              )}
            </Card>
            <Collapse
              items={[{
                key: 'professional-sources',
                label: englishDemo ? 'Sources and reasoning trace (optional)' : '查看职业参考、公司背景和信息来源（可选）',
                children: (
                  <>
                    <Paragraph type="secondary">
                      {englishDemo
                        ? 'This section explains where the guidance comes from. Facts require citations; inferences are labeled.'
                        : '以下内容用于解释建议从哪里来，不需要为了完成简历优化而阅读。事实必须带引用；推断会明确标识。'}
                    </Paragraph>
                    <div className="advisor-layer-grid">
                      {Object.entries(LAYER_META).map(([type]) => (
                        <ProfileLayer key={type} type={type} layer={profile.layers?.[type]} />
                      ))}
                    </div>
                    {profile?.snapshot && (
                      <Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
                        信息版本：{profile.snapshot.snapshot_hash.slice(0, 12)} ·
                        {profile.snapshot.status === 'employer_confirmed' ? ' 企业已确认' : ' 待企业确认'}
                      </Paragraph>
                    )}
                  </>
                ),
              }]}
            />
          </Space>
        ) : (
          <Empty description={englishDemo ? 'Select a target role' : '请选择目标岗位'} />
        )}
      </Spin>

      <Card
        className="content-card"
        title={englishDemo ? 'Evidence Gap → Next Best Action' : '你现在最该做什么'}
      >
        {diagnostic ? (
          <div className="advisor-readiness-grid">
            <div>
              <CandidateActionMap
                diagnostic={diagnostic}
                onResolveIssue={resolveIssueInResume}
                onHypothesisStatus={updateHypothesis}
              />
              <Collapse
                style={{ marginTop: 12 }}
                items={[{
                  key: 'readiness-reference',
                  label: englishDemo ? 'Readiness reference (optional)' : '查看准备度参考（可选）',
                  children: (
                    <>
                      <Text>{englishDemo ? 'Current evidence coverage' : '当前材料覆盖情况'}</Text>
                      <Progress percent={Number(diagnostic.readiness?.current || 0)} />
                      <Text>{englishDemo ? 'Scenario after completing the plan' : '完成计划后的参考情景'}</Text>
                      <Progress
                        strokeColor="#94a3b8"
                        percent={Number(diagnostic.readiness?.future_scenario || 0)}
                      />
                      <Text type="secondary">{diagnostic.readiness?.notice}</Text>
                    </>
                  ),
                }]}
              />
            </div>
            <div>
              <PersonalizedGuidancePanel
                guidance={diagnostic.personalized_guidance}
                fallback={diagnostic.decision_trace?.recommended_next_actions || []}
                title={englishDemo ? 'Apply and build evidence in this order' : '按这个顺序投递和提升'}
              />
              <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
                <Button type="primary" block onClick={openApplicationWorkbench}>
                  {englishDemo ? 'Build an Evidence-Based Application Plan' : '生成当前可投版本并安排提升行动'}
                </Button>
                {profile?.job?.advisor_private && (
                  <Button
                    block
                    loading={recordingApplication}
                    onClick={() => Modal.confirm({
                      title: '确认你已在站外完成投递？',
                      content: '这里只记录进度，不会替你向企业提交，也不会把简历发送给企业。',
                      okText: '确认已投递并记录',
                      cancelText: '取消',
                      onOk: recordExternalApplication,
                    })}
                  >
                    我已在站外投递，记录进度
                  </Button>
                )}
                <Button block onClick={() => navigate('/candidate/applied-jobs')}>
                  {englishDemo ? 'View Application Outcomes' : '查看投递、面试和录用结果'}
                </Button>
                <Text type="secondary">
                  {englishDemo
                    ? 'Only confirmed facts are used. Completed tasks must return as new evidence.'
                    : '改写只使用你已确认的履历事实；提升行动完成后仍需补充新经历或证据。'}
                </Text>
              </Space>
            </div>
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={englishDemo
              ? 'Select a resume to reason from the role requirements and evidence you provided.'
              : '选择简历后生成；结果只依据当前岗位要求与你已提供的材料。'}
          />
        )}
      </Card>

      <Card
        className="content-card advisor-chat"
        title={<Space><RobotOutlined />{englishDemo ? 'Ask the Role Advisor' : '问岗位顾问'}</Space>}
      >
        <List
          dataSource={messages}
          locale={{
            emptyText: englishDemo
              ? 'Try: What should I prepare first? Which experience best supports this role?'
              : '可以问：我应该优先准备什么？我的哪段经历最适合这个岗位？',
          }}
          renderItem={(item) => (
            <List.Item className="advisor-message-row">
              <AdvisorAnswer item={item} />
            </List.Item>
          )}
        />
        <Space.Compact style={{ width: '100%' }}>
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 5 }}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={englishDemo ? 'Example: Which evidence gap should I address first?' : '例如：我应该先改哪一段经历？'}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={sending}
            disabled={!jobId}
            onClick={send}
          >
            {englishDemo ? 'Send' : '发送'}
          </Button>
        </Space.Compact>
      </Card>
    </div>
  );
}

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
  FundOutlined,
  LinkOutlined,
  RobotOutlined,
  SendOutlined,
  SolutionOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import { createIdempotencyTracker } from '../../utils/idempotency';
import PersonalizedGuidancePanel from '../../components/PersonalizedGuidancePanel';

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
  const diagnosticIdempotency = useRef(createIdempotencyTracker('advisor-diagnostic'));
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
  const jobId = searchParams.get('job_id') || '';

  const jobOptions = useMemo(
    () => jobs.map((job) => ({
      value: job.id,
      label: `${job.title}${job.company_name ? ` · ${job.company_name}` : ''}`,
    })),
    [jobs],
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

  const generateReadiness = async () => {
    if (!jobId || !selectedResumeId) {
      message.warning('请先选择一份简历');
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
                岗位准备助手
              </Title>
              <Text type="secondary">
                选择岗位和简历，直接看你最该准备什么。
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
              placeholder="选择目标岗位"
              onChange={(value) => setSearchParams({ job_id: value })}
            />
            <Select
              allowClear
              value={selectedResumeId}
              className="advisor-resume-select"
              placeholder="选择简历以核对你的材料"
              onChange={setSelectedResumeId}
              options={resumes.map((resume, index) => ({
                value: resume.id,
                label: `${resume.parsed?.name || `简历 ${index + 1}`} · ${resume.parsed?.expected_job_title || '未填写方向'}`,
              }))}
            />
            <Button
              type="primary"
              loading={diagnosing}
              disabled={!jobId || !selectedResumeId}
              onClick={generateReadiness}
            >
              分析我该先做什么
            </Button>
          </Space>
          {profile?.snapshot?.is_stale && (
            <Alert
              showIcon
              type="warning"
              message="部分来源已经过期"
              description="顾问不会继续把过期来源用于新回答；请等待管理员发布新版本。"
            />
          )}
        </Space>
      </Card>

      <Spin spinning={loading}>
        {profile ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Card className="content-card" title="这个岗位最看重什么">
              {targetRequirements.length ? (
                <List
                  size="small"
                  dataSource={targetRequirements.slice(0, 6)}
                  renderItem={(item) => <List.Item>{item.text}</List.Item>}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="这个岗位的明确要求还不完整，可以先查看完整岗位说明"
                />
              )}
            </Card>
            <Collapse
              items={[{
                key: 'professional-sources',
                label: '查看职业参考、公司背景和信息来源（可选）',
                children: (
                  <>
                    <Paragraph type="secondary">
                      以下内容用于解释建议从哪里来，不需要为了完成简历优化而阅读。
                      事实必须带引用；推断会明确标识。
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
          <Empty description="请选择目标岗位" />
        )}
      </Spin>

      <Card
        className="content-card"
        title="你现在最该做什么"
      >
        {diagnostic ? (
          <div className="advisor-readiness-grid">
            <div>
              <Alert
                showIcon
                type="info"
                message="先完成右侧最重要的 1—3 项，不需要一次把简历全部重写"
              />
              <Collapse
                style={{ marginTop: 12 }}
                items={[{
                  key: 'readiness-reference',
                  label: '查看准备度参考（可选）',
                  children: (
                    <>
                      <Text>当前材料覆盖情况</Text>
                      <Progress percent={Number(diagnostic.readiness?.current || 0)} />
                      <Text>完成计划后的参考情景</Text>
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
              />
            </div>
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="选择简历后生成；结果只依据当前岗位要求与你已提供的材料。"
          />
        )}
      </Card>

      <Card
        className="content-card advisor-chat"
        title={<Space><RobotOutlined />问岗位顾问</Space>}
      >
        <List
          dataSource={messages}
          locale={{
            emptyText: '可以问：我应该优先准备什么？我的哪段经历最适合这个岗位？',
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
            placeholder="例如：我应该先改哪一段经历？"
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
            发送
          </Button>
        </Space.Compact>
      </Card>
    </div>
  );
}

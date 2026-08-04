import {
  useCallback, useEffect, useRef, useState,
} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Input,
  List,
  message,
  Popconfirm,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import {
  ReloadOutlined,
  EnvironmentOutlined,
  DollarOutlined,
  FileSearchOutlined,
  MessageOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import MatchEvaluationPanel from '../../components/MatchEvaluationPanel';
import ApplicationMessageBubble from '../../components/ApplicationMessageBubble';
import { getStatusConfig } from '../../constants/applicationStatus';
import { extractClaimText, resumeRewriteLink } from '../../utils/clarification';

const { Text } = Typography;

function openClaimsFromApp(app) {
  const threads = (app?.claim_threads || []).filter((t) => t.status === 'open');
  if (threads.length) return threads;
  // 回退：从澄清请求构造（旧数据）
  return (app?.clarification_requests || [])
    .filter((r) => r.claim_id || r.claim_text)
    .map((r) => ({
      claim_id: r.claim_id,
      claim_text: r.claim_text || extractClaimText(r),
      status: 'open',
      request_message_id: r.message_id,
    }));
}

const canPerform = (application, action) => (
  application?.allowed_actions?.candidate?.includes(action) ?? false
);

const externalStatusText = {
  submitted: '已记录投递',
  interview_invited: '已进入面试',
  rejected: '未通过',
  accepted: '已录用',
};

export default function AppliedJobs() {
  const [searchParams] = useSearchParams();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currentApplication, setCurrentApplication] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [replyDraft, setReplyDraft] = useState('');
  const [replying, setReplying] = useState(false);
  const [activeClaimId, setActiveClaimId] = useState(null);
  const [replySuccess, setReplySuccess] = useState({});
  const [evalExpanded, setEvalExpanded] = useState(false);
  const [updatingOutcome, setUpdatingOutcome] = useState(null);
  const messagesEndRef = useRef(null);
  const autoOpened = useRef(false);

  const fetchApplications = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await api.get('/applications/mine/evaluations');
      setApplications(res.data || []);
      return res.data || [];
    } catch {
      message.error('加载已申请岗位失败');
      return [];
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadMessages = useCallback(async (app) => {
    setCurrentApplication(app);
    if (app.external_tracking) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    const opens = openClaimsFromApp(app);
    setActiveClaimId(opens[0]?.claim_id || null);
    setReplyDraft('');
    try {
      const res = await api.get(`/applications/${app.id}/messages`);
      setMessages(res.data || []);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch {
      message.error('加载对话失败');
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const updateExternalOutcome = async (app, status) => {
    setUpdatingOutcome(`${app.id}:${status}`);
    try {
      const res = await api.patch(`/applications/external-tracking/${app.id}/status`, { status });
      const updated = res.data?.application;
      setApplications((current) => current.map((item) => (item.id === app.id ? { ...item, ...updated } : item)));
      setCurrentApplication((current) => (current?.id === app.id ? { ...current, ...updated } : current));
      message.success('站外申请结果已更新');
    } catch (err) {
      message.error(getApiErrorMessage(err, '更新申请结果失败'));
    } finally {
      setUpdatingOutcome(null);
    }
  };

  const submitClarificationReply = async () => {
    const appId = currentApplication?.id;
    const body = replyDraft.trim();
    const openClaims = openClaimsFromApp(currentApplication);
    if (!appId || !body) {
      message.warning('请填写澄清回复');
      return;
    }
    if (openClaims.length > 1 && !activeClaimId) {
      message.warning('请先选择要回复的 Claim');
      return;
    }
    const claimId = activeClaimId || openClaims[0]?.claim_id || null;
    if (openClaims.length > 1 && !claimId) {
      message.warning('请选择要回复的 Claim');
      return;
    }

    setReplying(true);
    try {
      const payload = { body };
      if (claimId) payload.claim_id = claimId;
      const res = await api.post(`/applications/${appId}/clarification-response`, payload);
      const answeredClaim = openClaims.find((c) => c.claim_id === claimId);
      const nextStatus = res.data?.application?.status
        || res.data?.status
        || (res.data?.open_claim_count > 0 ? 'needs_clarification' : 'clarified');
      setReplyDraft('');
      setReplySuccess((prev) => ({
        ...prev,
        [appId]: {
          sentAt: new Date().toISOString(),
          status: nextStatus,
          claimId,
          claimText: answeredClaim?.claim_text || extractClaimText(answeredClaim),
          remainingOpen: res.data?.open_claim_count ?? 0,
        },
      }));
      message.success(
        nextStatus === 'needs_clarification'
          ? '该 Claim 已回复，仍有其他待澄清项'
          : '澄清回复已发送',
      );
      window.dispatchEvent(new Event('clarification-updated'));
      const apps = await fetchApplications(true);
      const updated = apps.find((a) => a.id === appId);
      if (updated) {
        setCurrentApplication(updated);
        const stillOpen = openClaimsFromApp(updated);
        setActiveClaimId(stillOpen[0]?.claim_id || null);
      }
      const msgRes = await api.get(`/applications/${appId}/messages`);
      setMessages(msgRes.data || []);
      if (res.data?.application) {
        setCurrentApplication((prev) => ({ ...prev, ...res.data.application }));
      }
    } catch (err) {
      message.error(getApiErrorMessage(err, '发送失败'));
    } finally {
      setReplying(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => fetchApplications(), 0);
    return () => clearTimeout(timer);
  }, [fetchApplications]);

  useEffect(() => {
    if (loading || autoOpened.current || !applications.length) return;
    const requestedId = searchParams.get('applicationId');
    const requested = applications.find((a) => a.id === requestedId);
    if (requested) {
      autoOpened.current = true;
      const timer = setTimeout(() => loadMessages(requested), 0);
      return () => clearTimeout(timer);
    }
    const pending = applications.find((a) => a.status === 'needs_clarification');
    if (pending) {
      autoOpened.current = true;
      const timer = setTimeout(() => loadMessages(pending), 0);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [loading, applications, loadMessages, searchParams]);

  const pendingClarifications = applications.filter((application) => (
    canPerform(application, 'reply_clarification')
  ));
  const successInfo = currentApplication ? replySuccess[currentApplication.id] : null;
  const openClaims = openClaimsFromApp(currentApplication);
  const activeClaim = openClaims.find((c) => c.claim_id === activeClaimId) || openClaims[0];
  const activeClaimText = activeClaim?.claim_text
    || successInfo?.claimText
    || extractClaimText(currentApplication?.pending_clarification)
    || '';
  const pastResponses = currentApplication?.clarification_responses || [];
  const stillNeedsClarification = canPerform(
    currentApplication,
    'reply_clarification',
  );

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        className="content-card"
        title={(
          <Space>
            <FileSearchOutlined />
            投递与结果
          </Space>
        )}
        extra={(
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => fetchApplications(true)}>
            刷新
          </Button>
        )}
      >
        {pendingClarifications.length > 0 && (
          <Alert
            type="warning"
            showIcon
            icon={<MessageOutlined />}
            style={{ marginBottom: 16 }}
            message={(
              <Space>
                需要你补充说明的申请
                <Tag color="orange">{pendingClarifications.length}</Tag>
              </Space>
            )}
            description="招聘方对简历中的某些描述有疑问，请按每条 Claim 分别补充真实细节。"
          />
        )}

        <Spin spinning={loading || refreshing}>
          {applications.length === 0 ? (
            <Empty description="暂无投递记录" image={Empty.PRESENTED_IMAGE_SIMPLE}>
              <Link to="/candidate/browse-jobs">
                <Button type="primary">去浏览岗位</Button>
              </Link>
            </Empty>
          ) : (
            <List
              dataSource={applications}
              renderItem={(app) => {
                const statusCfg = getStatusConfig(app.status);
                const isActive = currentApplication?.id === app.id;
                return (
                  <List.Item
                    style={{
                      background: isActive ? '#f8fafc' : undefined,
                      borderRadius: 8,
                      padding: '12px 8px',
                    }}
                    extra={app.external_tracking ? (
                      <Button onClick={() => loadMessages(app)}>更新结果</Button>
                    ) : (
                      <Button
                        type={canPerform(app, 'reply_clarification') ? 'primary' : 'default'}
                        icon={<MessageOutlined />}
                        onClick={() => loadMessages(app)}
                      >
                        {canPerform(app, 'reply_clarification') ? '回复澄清' : '查看对话'}
                      </Button>
                    )}
                  >
                    <List.Item.Meta
                      title={(
                        <Space wrap>
                          <span style={{ fontWeight: 600 }}>{app.job_title || '未知岗位'}</span>
                          <Tag color={statusCfg.color}>
                            {app.external_tracking ? externalStatusText[app.status] : statusCfg.text}
                          </Tag>
                          {app.external_tracking && <Tag>站外记录</Tag>}
                          {canPerform(app, 'reply_clarification') && (
                            <Tag color="orange" icon={<MessageOutlined />}>
                              待回复{app.open_claim_count ? ` · ${app.open_claim_count}` : ''}
                            </Tag>
                          )}
                        </Space>
                      )}
                      description={(
                        <Space wrap style={{ color: '#64748b', fontSize: 13 }}>
                          <EnvironmentOutlined /> {app.job_location || '不限'}
                          <DollarOutlined /> {app.job_salary || '面议'}
                          <span>
                            {app.external_tracking ? '记录：' : '申请：'}
                            {app.created_at ? new Date(app.created_at).toLocaleString() : '—'}
                          </span>
                        </Space>
                      )}
                    />
                  </List.Item>
                );
              }}
            />
          )}
        </Spin>
      </Card>

      {currentApplication && (
        currentApplication.external_tracking ? (
          <Card
            className="content-card"
            title={`站外申请进度 · ${currentApplication.job_title || '未知岗位'}`}
          >
            <Alert
              type="info"
              showIcon
              message="这是你记录的站外进度"
              description="平台没有替你向企业提交申请；结果由你根据实际进展更新。"
              style={{ marginBottom: 16 }}
            />
            <Space wrap>
              {currentApplication.status === 'submitted' && (
                <Popconfirm
                  title="确认已进入面试？"
                  onConfirm={() => updateExternalOutcome(currentApplication, 'interview_invited')}
                >
                  <Button loading={updatingOutcome === `${currentApplication.id}:interview_invited`}>
                    记录进入面试
                  </Button>
                </Popconfirm>
              )}
              {['submitted', 'interview_invited'].includes(currentApplication.status) && (
                <>
                  <Popconfirm
                    title="确认本次申请未通过？"
                    onConfirm={() => updateExternalOutcome(currentApplication, 'rejected')}
                  >
                    <Button danger loading={updatingOutcome === `${currentApplication.id}:rejected`}>
                      记录未通过
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    title="确认已收到录用结果？"
                    onConfirm={() => updateExternalOutcome(currentApplication, 'accepted')}
                  >
                    <Button type="primary" loading={updatingOutcome === `${currentApplication.id}:accepted`}>
                      记录录用
                    </Button>
                  </Popconfirm>
                </>
              )}
              {['rejected', 'accepted'].includes(currentApplication.status) && (
                <Tag color={getStatusConfig(currentApplication.status).color}>
                  {externalStatusText[currentApplication.status]}
                </Tag>
              )}
            </Space>
          </Card>
        ) : (
        <Row gutter={16}>
          <Col xs={24} lg={16}>
            <Card
              className="content-card"
              title={`与招聘方澄清 · ${currentApplication.job_title || '未知岗位'}`}
              extra={(
                <Tag color={getStatusConfig(currentApplication.status).color}>
                  {getStatusConfig(currentApplication.status).text}
                </Tag>
              )}
            >
              {successInfo && (
                <Alert
                  type={stillNeedsClarification ? 'info' : 'success'}
                  showIcon
                  icon={<CheckCircleOutlined />}
                  style={{ marginBottom: 12 }}
                  message={
                    stillNeedsClarification
                      ? '已回复所选 Claim，仍有待澄清项'
                      : '已发送给招聘方'
                  }
                  description={(
                    <Space direction="vertical" size={6}>
                      <span>
                        当前状态：{getStatusConfig(currentApplication.status).text}
                        {successInfo.claimText ? ` · 刚回复：${successInfo.claimText}` : ''}
                      </span>
                      {activeClaimText && !stillNeedsClarification && (
                        <Link to={resumeRewriteLink(currentApplication.resume_id, activeClaimText)}>
                          <Button type="primary" size="small">
                            针对本次 claim 去忠实改写
                          </Button>
                        </Link>
                      )}
                    </Space>
                  )}
                />
              )}

              {!successInfo && currentApplication.status === 'clarified' && (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                  style={{ marginBottom: 12 }}
                  message="您已回复澄清请求"
                  description="已提交说明，等待招聘方复核；这不代表相关事实已被验证。"
                />
              )}

              {currentApplication.status === 'clarification_closed' && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="招聘方已关闭澄清"
                  description="候选人未完成全部说明；此状态不表示已澄清。"
                />
              )}

              {pastResponses.length > 0 && currentApplication.status !== 'needs_clarification' && (
                <Card size="small" title="我的澄清回复记录" style={{ marginBottom: 12 }}>
                  <List
                    size="small"
                    dataSource={pastResponses}
                    renderItem={(item) => (
                      <List.Item style={{ padding: '8px 0', alignItems: 'flex-start' }}>
                        <div style={{ width: '100%' }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                            {item.claim_id ? ` · ${item.claim_id}` : ''}
                          </Text>
                          <div style={{
                            marginTop: 4, padding: '8px 10px', borderRadius: 6,
                            background: '#ecfdf5', fontSize: 13, whiteSpace: 'pre-wrap',
                          }}
                          >
                            {item.body}
                          </div>
                        </div>
                      </List.Item>
                    )}
                  />
                </Card>
              )}

              <Spin spinning={messagesLoading}>
                <List
                  dataSource={messages}
                  locale={{ emptyText: '暂无消息' }}
                  style={{ maxHeight: 400, overflow: 'auto', marginBottom: 16 }}
                  renderItem={(item) => (
                    <List.Item style={{ justifyContent: item.is_mine ? 'flex-end' : 'flex-start' }}>
                      <ApplicationMessageBubble item={item} bodyFontSize={14} />
                    </List.Item>
                  )}
                />
                <div ref={messagesEndRef} />
              </Spin>

              {stillNeedsClarification ? (
                <div>
                  {openClaims.length > 0 && (
                    <Card size="small" title="待回复的 Claim" style={{ marginBottom: 12 }}>
                      <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        {openClaims.map((claim) => {
                          const selected = (claim.claim_id || '') === (activeClaimId || '');
                          return (
                            <Button
                              key={claim.claim_id || claim.thread_key || claim.claim_text}
                              type={selected ? 'primary' : 'default'}
                              block
                              style={{ textAlign: 'left', height: 'auto', whiteSpace: 'normal' }}
                              onClick={() => setActiveClaimId(claim.claim_id)}
                            >
                              <div>
                                <Text strong style={{ color: selected ? '#fff' : undefined }}>
                                  {claim.claim_text || claim.claim_id || '未命名主张'}
                                </Text>
                                {claim.claim_id && (
                                  <div style={{ fontSize: 11, opacity: 0.8 }}>{claim.claim_id}</div>
                                )}
                              </div>
                            </Button>
                          );
                        })}
                      </Space>
                    </Card>
                  )}
                  <Input.TextArea
                    rows={3}
                    value={replyDraft}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    placeholder={
                      activeClaim?.claim_text
                        ? `针对「${activeClaim.claim_text.slice(0, 40)}」补充真实细节…`
                        : '请补充说明：你的实际角色、具体贡献、技术栈或项目背景…'
                    }
                    style={{ marginBottom: 8 }}
                  />
                  <Button
                    type="primary"
                    loading={replying}
                    onClick={submitClarificationReply}
                    disabled={
                      !canPerform(currentApplication, 'reply_clarification')
                      || (openClaims.length > 1 && !activeClaimId)
                    }
                  >
                    发送澄清回复
                    {activeClaim?.claim_id ? `（${activeClaim.claim_id}）` : ''}
                  </Button>
                </div>
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message={
                    currentApplication.status === 'clarified'
                      ? '您已回复澄清请求，招聘方将结合说明进一步复核'
                      : currentApplication.status === 'clarification_closed'
                        ? '招聘方已关闭澄清，候选人未完成全部说明'
                      : '当前无需澄清回复'
                  }
                />
              )}
            </Card>
          </Col>

          <Col xs={24} lg={8}>
            <Card className="content-card" title="岗位匹配评估" size="small">
              <Collapse
                activeKey={evalExpanded ? ['eval'] : []}
                onChange={(keys) => setEvalExpanded(keys.includes('eval'))}
                items={[{
                  key: 'eval',
                  label: currentApplication.evaluation
                    ? `${currentApplication.evaluation.match_score} 分 · 可提升空间 ${currentApplication.evaluation.potential_score}`
                    : '展开查看',
                  children: <MatchEvaluationPanel evaluation={currentApplication.evaluation} />,
                }]}
              />
            </Card>
          </Col>
        </Row>
        )
      )}
    </Space>
  );
}

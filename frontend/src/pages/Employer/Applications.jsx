import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import {
  Button, Card, Col, Input, List, message, Modal, Row, Select, Space, Spin, Tag, Typography, Segmented, Alert,
} from 'antd';
import { MessageOutlined, BellOutlined, CheckOutlined, SendOutlined, CloseOutlined } from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import ResumeCredibilityPanel from '../../components/ResumeCredibilityPanel';
import ApplicationMessageBubble from '../../components/ApplicationMessageBubble';
import {
  CLARIFICATION_QUICK_FILTERS,
  EMPLOYER_STATUS_OPTIONS,
  getStatusConfig,
} from '../../constants/applicationStatus';

const { Text } = Typography;

const applyQuickFilter = (items, filterKey) => {
  const cfg = CLARIFICATION_QUICK_FILTERS.find((f) => f.value === filterKey);
  if (!cfg?.statuses) return items;
  return items.filter((application) => cfg.statuses.includes(application.status));
};

const STATUS_ACTION = {
  viewed: 'mark_viewed',
  interview_invited: 'invite_interview',
  rejected: 'reject',
  accepted: 'accept',
};

const allowedFor = (application, role, action) => (
  application?.allowed_actions?.[role]?.includes(action) ?? false
);

export default function Applications() {
  const { jobId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [allApplications, setAllApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [quickFilter, setQuickFilter] = useState('');
  const [currentApplication, setCurrentApplication] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [closingClarification, setClosingClarification] = useState(false);
  const [closeTargetId, setCloseTargetId] = useState(null);
  const [closeReason, setCloseReason] = useState('');
  const [highlightMessageId, setHighlightMessageId] = useState(null);
  const [reviewedIds, setReviewedIds] = useState(new Set());
  const messagesEndRef = useRef(null);
  const deepLinkHandled = useRef(false);

  const statusCounts = allApplications.reduce((acc, app) => {
    acc[app.status] = (acc[app.status] || 0) + 1;
    return acc;
  }, {});

  const applications = useMemo(
    () => applyQuickFilter(allApplications, quickFilter),
    [allApplications, quickFilter],
  );
  const allowedStatusOptions = useMemo(
    () => EMPLOYER_STATUS_OPTIONS.filter((option) => (
      option.value === currentApplication?.status
      || allowedFor(
        currentApplication,
        'employer',
        STATUS_ACTION[option.value],
      )
    )),
    [currentApplication],
  );

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/applications/job/${jobId}`);
      const items = res.data || [];
      setAllApplications(items);
      setCurrentApplication((prev) => {
        if (!prev?.id) return prev;
        const refreshed = items.find((item) => item.id === prev.id);
        return refreshed ? { ...prev, ...refreshed } : prev;
      });
      return items;
    } catch (err) {
      message.error(`加载申请记录失败：${getApiErrorMessage(err, '请重试')}`);
      return [];
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const loadMessages = useCallback(async (application, options = {}) => {
    const { scrollToLatestResponse = false, silent = false } = options;
    if (!silent) {
      setCurrentApplication(application);
      setMessagesLoading(true);
      setHighlightMessageId(null);
    }
    try {
      const res = await api.get(`/applications/${application.id}/messages`);
      const msgs = res.data || [];
      setMessages(msgs);
      if (!silent) {
        const updated = allApplications.find((a) => a.id === application.id);
        const nextApplication = {
          ...application,
          ...(updated || {}),
          ...(application.status === 'submitted' ? { status: 'viewed' } : {}),
        };
        setCurrentApplication(nextApplication);
        if (application.status === 'submitted') {
          setAllApplications((prev) => prev.map((item) => (
            item.id === application.id ? { ...item, status: 'viewed' } : item
          )));
        }
      }

      if (scrollToLatestResponse || application.status === 'clarified') {
        const latestResponse = [...msgs].reverse().find((m) => m.message_kind === 'clarification_response');
        if (latestResponse) {
          setHighlightMessageId(latestResponse.id);
          setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        }
      }
    } catch {
      if (!silent) message.error('加载对话失败');
    } finally {
      if (!silent) setMessagesLoading(false);
    }
  }, [allApplications]);

  const sendMessage = async () => {
    const body = messageText.trim();
    if (!body || !currentApplication?.id) return;

    setSending(true);
    try {
      const res = await api.post(`/applications/${currentApplication.id}/messages`, { body });
      setMessages((prev) => [...prev, res.data]);
      setMessageText('');
    } catch (err) {
      message.error(`发送失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setSending(false);
    }
  };

  const updateStatus = async (newStatus) => {
    if (!currentApplication?.id || !newStatus) return;
    if (newStatus === 'interview_invited' && (currentApplication.open_claim_count || 0) > 0) {
      message.warning('仍有待回复 Claim，请先完成回复或明确关闭澄清');
      return;
    }
    setUpdatingStatus(true);
    try {
      // 邀请面试：走统一邀请接口，同步 InterviewInvitation + application 状态
      if (newStatus === 'interview_invited' && currentApplication.resume_id) {
        await api.post('/invitations/send', {
          job_id: jobId,
          resume_id: currentApplication.resume_id,
          application_id: currentApplication.id,
          message: '招聘方通过申请详情发起面试邀请',
        });
        await fetchApplications();
        const refreshed = (await api.get(`/applications/job/${jobId}`)).data || [];
        const updated = refreshed.find((a) => a.id === currentApplication.id);
        if (updated) setCurrentApplication((prev) => ({ ...prev, ...updated }));
        await loadMessages({ ...currentApplication, status: 'interview_invited' }, { silent: true });
        message.success('已发送面试邀请并同步申请状态');
        return;
      }
      const res = await api.patch(`/applications/${currentApplication.id}/status`, {
        status: newStatus,
      });
      const updated = res.data.application;
      setCurrentApplication((prev) => ({ ...prev, ...updated }));
      setAllApplications((prev) => prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)));
      message.success('申请状态已更新');
    } catch (err) {
      message.error(getApiErrorMessage(err, '状态更新失败'));
    } finally {
      setUpdatingStatus(false);
    }
  };

  const closeClarification = async () => {
    const appId = closeTargetId;
    const reason = closeReason.trim();
    if (!appId || !reason) {
      message.warning('请填写关闭原因');
      return;
    }
    setClosingClarification(true);
    try {
      const res = await api.post(`/applications/${appId}/clarification/close`, {
        reason,
      });
      const updated = res.data.application;
      if (updated) {
        setCurrentApplication((prev) => (prev?.id === appId ? { ...prev, ...updated } : prev));
        setAllApplications((prev) => prev.map((a) => (a.id === appId ? { ...a, ...updated } : a)));
      }
      message.success('已人工关闭澄清并留痕');
      setCloseTargetId(null);
      setCloseReason('');
    } catch (err) {
      message.error(getApiErrorMessage(err, '关闭澄清失败'));
    } finally {
      setClosingClarification(false);
    }
  };

  const markReviewed = async (appId) => {
    try {
      const res = await api.post(`/applications/${appId}/mark-reviewed`, {});
      const updated = res.data.application;
      setReviewedIds((prev) => new Set([...prev, appId]));
      if (updated) {
        setCurrentApplication((prev) => (prev?.id === appId ? { ...prev, ...updated } : prev));
        setAllApplications((prev) => prev.map((a) => (a.id === appId ? { ...a, ...updated } : a)));
      }
      window.dispatchEvent(new Event('employer-inbox-updated'));
      message.success('已标记复核完成');
    } catch (err) {
      message.error(getApiErrorMessage(err, '标记复核失败'));
    }
  };

  const scrollToAuditPanel = () => {
    document.getElementById('employer-credibility-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    message.info('可在右侧审计面板再次发起澄清');
  };

  const handleClarificationSent = async (result) => {
    const refreshedApplications = await fetchApplications();
    const appId = result?.application_id || result?.application?.id || currentApplication?.id;
    if (appId) {
      const msgRes = await api.get(`/applications/${appId}/messages`);
      setMessages(msgRes.data || []);
      const refreshed = refreshedApplications?.find((a) => a.id === appId);
      if (refreshed || result?.application) {
        setCurrentApplication((prev) => ({
          ...(prev?.id === appId ? prev : {}),
          ...(refreshed || {}),
          ...(result?.application || {}),
        }));
      }
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => fetchApplications(), 0);
    return () => clearTimeout(timer);
  }, [fetchApplications]);

  // 打开对话后短轮询消息，减少两端刷新断裂
  useEffect(() => {
    if (!currentApplication?.id) return undefined;
    const timer = setInterval(() => {
      loadMessages(currentApplication, { silent: true });
      fetchApplications();
    }, 8000);
    return () => clearInterval(timer);
  }, [currentApplication, fetchApplications, loadMessages]);

  useEffect(() => {
    if (loading || deepLinkHandled.current) return undefined;
    const timer = setTimeout(() => {
      const applicationId = searchParams.get('applicationId');
      if (!applicationId) return;

      deepLinkHandled.current = true;
      setSearchParams({}, { replace: true });

      if (!allApplications.length) {
        message.warning('暂无申请记录');
        return;
      }

      const target = allApplications.find((application) => application.id === applicationId);
      if (target) {
        const cfg = CLARIFICATION_QUICK_FILTERS.find((f) => f.value === quickFilter);
        if (cfg?.statuses && !cfg.statuses.includes(target.status)) {
          setQuickFilter('');
        }
        loadMessages(target);
      } else {
        message.warning('未找到对应申请记录，请从列表中选择');
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [loading, allApplications, searchParams, quickFilter, setSearchParams, loadMessages]);

  const quickFilterOptions = CLARIFICATION_QUICK_FILTERS.map((f) => {
    let count = allApplications.length;
    if (f.statuses) {
      count = allApplications.filter((a) => f.statuses.includes(a.status)).length;
    }
    return {
      label: `${f.label}${count > 0 ? ` (${count})` : ''}`,
      value: f.value,
    };
  });

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        className="content-card"
        title="岗位申请记录"
        extra={(
          <Space>
            <Link to={`/employer/candidates/${jobId}`}><Button>匹配候选人</Button></Link>
            <Link to="/employer/my-jobs"><Button>返回岗位列表</Button></Link>
          </Space>
        )}
      >
        <Segmented
          value={quickFilter}
          onChange={setQuickFilter}
          options={quickFilterOptions}
          style={{ marginBottom: 16 }}
          block
        />

        {(statusCounts.needs_clarification > 0 || statusCounts.clarified > 0) && (
          <Space wrap style={{ marginBottom: 12 }}>
            {statusCounts.needs_clarification > 0 && (
              <Tag color="orange" icon={<BellOutlined />}>
                {statusCounts.needs_clarification} 条等待候选人回复
              </Tag>
            )}
            {statusCounts.clarified > 0 && (
              <Tag color="cyan" icon={<MessageOutlined />}>
                {statusCounts.clarified} 条候选人已回复，请复核
              </Tag>
            )}
          </Space>
        )}

        <Spin spinning={loading}>
          <List
            dataSource={applications}
            locale={{
              emptyText: (
                <div style={{ padding: '24px 0', textAlign: 'center' }}>
                  <p style={{ color: '#64748b', marginBottom: 12 }}>
                    {quickFilter ? '当前筛选下暂无申请记录' : '暂无申请记录'}
                  </p>
                  <p style={{ color: '#94a3b8', fontSize: 13, maxWidth: 480, margin: '0 auto' }}>
                    候选人主动投递或对匹配候选人发起澄清后，记录会出现在此处。
                    可在
                    <Link to={`/employer/candidates/${jobId}`}> 匹配候选人 </Link>
                    页运行审计并直接发起澄清。
                  </p>
                </div>
              ),
            }}
            renderItem={(item) => {
              const statusCfg = getStatusConfig(item.status, 'employer');
              return (
                <List.Item
                  extra={(
                    <Button
                      type={item.status === 'clarified' ? 'primary' : 'default'}
                      icon={<MessageOutlined />}
                      onClick={() => loadMessages(item, {
                        scrollToLatestResponse: item.status === 'clarified',
                      })}
                    >
                      {item.status === 'clarified' ? '查看回复' : '对话'}
                    </Button>
                  )}
                >
                  <List.Item.Meta
                    title={(
                      <Space wrap>
                        <span>{`${item.candidate_name} · ${item.expected_title}`}</span>
                        {item.status === 'needs_clarification' && (
                          <Tag color="orange">等待候选人回复</Tag>
                        )}
                        {item.status === 'clarified' && (
                          <Tag color="cyan">
                            {(item.employer_reviewed_at || reviewedIds.has(item.id))
                              ? '已复核'
                              : '候选人已回复，请复核'}
                          </Tag>
                        )}
                        {(item.answered_unreviewed_count || 0) > 0 && item.status !== 'clarified' && (
                          <Tag color="cyan">有待复核回复</Tag>
                        )}
                      </Space>
                    )}
                    description={(
                      <Space direction="vertical" size={4}>
                        <Text type="secondary">
                          申请时间：{item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                        </Text>
                        {item.cover_letter && <Text>{item.cover_letter}</Text>}
                      </Space>
                    )}
                  />
                  <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
                </List.Item>
              );
            }}
          />
        </Spin>
      </Card>

      {currentApplication && (
        <Row gutter={16}>
          <Col xs={24} lg={14}>
            <Card
              className="content-card"
              title={`和 ${currentApplication.candidate_name} 对话`}
              extra={(
                <Space>
                  <Tag color={getStatusConfig(currentApplication.status, 'employer').color}>
                    {getStatusConfig(currentApplication.status, 'employer').text}
                  </Tag>
                  <Select
                    size="small"
                    style={{ width: 130 }}
                    placeholder="更新状态"
                    loading={updatingStatus}
                    value={currentApplication.status}
                    onChange={updateStatus}
                    options={allowedStatusOptions}
                  />
                </Space>
              )}
            >
              {currentApplication.status === 'clarified' && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="候选人已回复澄清，请复核后选择下一步"
                  description={(
                    <Space direction="vertical" size={8}>
                      <Text type="secondary">候选人已说明，不代表事实已验证。</Text>
                      <Space wrap>
                        <Button
                          size="small"
                          type="primary"
                          icon={<SendOutlined />}
                          loading={updatingStatus}
                          disabled={!allowedFor(currentApplication, 'employer', 'invite_interview')}
                          onClick={() => updateStatus('interview_invited')}
                        >
                          邀请面试
                        </Button>
                        <Button
                          size="small"
                          icon={<MessageOutlined />}
                          onClick={scrollToAuditPanel}
                          disabled={!allowedFor(currentApplication, 'employer', 'request_clarification')}
                        >
                          再次澄清
                        </Button>
                        <Button
                          size="small"
                          icon={<CheckOutlined />}
                          onClick={() => markReviewed(currentApplication.id)}
                          disabled={
                            !allowedFor(currentApplication, 'employer', 'mark_reviewed')
                            || Boolean(currentApplication.employer_reviewed_at)
                            || reviewedIds.has(currentApplication.id)
                          }
                        >
                          {(currentApplication.employer_reviewed_at || reviewedIds.has(currentApplication.id)) ? '已复核' : '标记已复核'}
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          loading={updatingStatus}
                          onClick={() => updateStatus('rejected')}
                          disabled={!allowedFor(currentApplication, 'employer', 'reject')}
                        >
                          不合适
                        </Button>
                      </Space>
                    </Space>
                  )}
                />
              )}
              {currentApplication.status === 'needs_clarification' && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="等待候选人回复澄清"
                  description={(
                    <Space wrap style={{ marginTop: 8 }}>
                      <Button
                        size="small"
                        loading={closingClarification}
                        onClick={() => setCloseTargetId(currentApplication.id)}
                        disabled={!allowedFor(currentApplication, 'employer', 'close_clarification')}
                      >
                        人工关闭澄清
                      </Button>
                    </Space>
                  )}
                />
              )}
              {currentApplication.status === 'clarification_closed' && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="招聘方已关闭澄清，候选人未说明"
                  description="该状态不代表候选人已完成回复，也不代表相关事实已验证。"
                />
              )}
              <Spin spinning={messagesLoading}>
                <List
                  dataSource={messages}
                  locale={{ emptyText: '暂无消息' }}
                  style={{ maxHeight: 360, overflow: 'auto', marginBottom: 16 }}
                  renderItem={(item) => (
                    <List.Item style={{ justifyContent: item.is_mine ? 'flex-end' : 'flex-start' }}>
                      <ApplicationMessageBubble
                        item={item}
                        maxWidth="72%"
                        highlight={item.id === highlightMessageId}
                      />
                    </List.Item>
                  )}
                />
                <div ref={messagesEndRef} />
              </Spin>
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  value={messageText}
                  onChange={(event) => setMessageText(event.target.value)}
                  onPressEnter={sendMessage}
                  placeholder="回复候选人..."
                  prefix={<MessageOutlined />}
                />
                <Button type="primary" loading={sending} onClick={sendMessage}>
                  发送
                </Button>
              </Space.Compact>
            </Card>
          </Col>
          <Col xs={24} lg={10} id="employer-credibility-panel">
            <ResumeCredibilityPanel
              applicationId={currentApplication.id}
              candidateName={currentApplication.candidate_name}
              onClarificationSent={handleClarificationSent}
            />
          </Col>
        </Row>
      )}
      <Modal
        title="人工关闭澄清"
        open={Boolean(closeTargetId)}
        okText="确认关闭"
        cancelText="取消"
        confirmLoading={closingClarification}
        okButtonProps={{ disabled: !closeReason.trim() }}
        onOk={closeClarification}
        onCancel={() => {
          setCloseTargetId(null);
          setCloseReason('');
        }}
      >
        <Alert
          type="warning"
          showIcon
          message="关闭后将标记为“候选人未说明”，不会显示为已澄清。"
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          rows={3}
          maxLength={500}
          showCount
          value={closeReason}
          onChange={(event) => setCloseReason(event.target.value)}
          placeholder="请填写关闭原因"
        />
      </Modal>
    </Space>
  );
}

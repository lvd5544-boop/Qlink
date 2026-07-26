import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Card,
  List,
  Tag,
  Button,
  message,
  Modal,
  Descriptions,
  Space,
  Spin,
  Typography,
  Form,
  Input,
  DatePicker,
  Alert,
  Drawer,
} from 'antd';
import {
  EyeOutlined,
  SendOutlined,
  AuditOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import ResumeCredibilityPanel from '../../components/ResumeCredibilityPanel';
import { getStatusConfig } from '../../constants/applicationStatus';

const { Text } = Typography;

export default function CandidateList() {
  const { jobId } = useParams();
  const [candidates, setCandidates] = useState([]);
  const [applicationByResume, setApplicationByResume] = useState({});
  const [loading, setLoading] = useState(true);

  const [selectedResume, setSelectedResume] = useState(null);
  const [resumeLoading, setResumeLoading] = useState(false);

  const [auditTarget, setAuditTarget] = useState(null);
  const [clarificationNotice, setClarificationNotice] = useState(null);

  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteResumeId, setInviteResumeId] = useState(null);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [matchRes, appRes] = await Promise.all([
        api.get(`/matches/job/${jobId}`),
        api.get(`/applications/job/${jobId}`).catch(() => ({ data: [] })),
      ]);
      setCandidates(matchRes.data || []);
      const map = {};
      (appRes.data || []).forEach((app) => {
        map[app.resume_id] = app;
      });
      setApplicationByResume(map);
    } catch {
      message.error('加载候选人失败');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    const timer = setTimeout(() => fetchData(), 0);
    return () => clearTimeout(timer);
  }, [fetchData]);

  const viewResume = async (resumeId) => {
    setResumeLoading(true);
    try {
      const res = await api.get(`/resume/${resumeId}`);
      setSelectedResume(res.data);
    } catch {
      message.error('无法加载简历详情');
    } finally {
      setResumeLoading(false);
    }
  };

  const openAudit = (item) => {
    const app = applicationByResume[item.resume_id];
    if (!app) {
      message.warning('匹配结果不构成候选人授权；需候选人真实投递后才能审计或澄清');
      return;
    }
    setAuditTarget({
      resumeId: item.resume_id,
      candidateName: item.candidate_name,
      applicationId: app?.id,
    });
  };

  const handleInvite = (resumeId) => {
    const app = applicationByResume[resumeId];
    if (!app) {
      message.warning('候选人尚未真实投递，当前不能发送邀请');
      return;
    }
    if ((app.open_claim_count || 0) > 0) {
      message.warning('仍有待回复 Claim，请先完成或关闭澄清');
      return;
    }
    setInviteResumeId(resumeId);
    setInviteModalOpen(true);
  };

  const handleClarificationSent = (result) => {
    const app = result?.application;
    const applicationId = result?.application_id || app?.id;
    if (app?.resume_id) {
      setApplicationByResume((prev) => ({
        ...prev,
        [app.resume_id]: app,
      }));
    } else if (auditTarget?.resumeId && applicationId) {
      setApplicationByResume((prev) => ({
        ...prev,
        [auditTarget.resumeId]: {
          ...(prev[auditTarget.resumeId] || {}),
          id: applicationId,
          resume_id: auditTarget.resumeId,
          status: app?.status || 'needs_clarification',
        },
      }));
    }
    setClarificationNotice({
      applicationId,
      resumeId: auditTarget?.resumeId,
    });
  };

  const applicationsLink = (applicationId) => (
    applicationId
      ? `/employer/applications/${jobId}?applicationId=${applicationId}`
      : `/employer/applications/${jobId}`
  );

  const sendInvitation = async (values) => {
    try {
      await api.post('/invitations/send', {
        job_id: jobId,
        resume_id: inviteResumeId,
        application_id: applicationByResume[inviteResumeId]?.id,
        message: values.message,
        proposed_time: values.proposed_time
          ? values.proposed_time.format('YYYY-MM-DD HH:mm')
          : null,
      });
      message.success('邀请已发送');
      setInviteModalOpen(false);
      form.resetFields();
    } catch (err) {
      message.error(`发送失败：${getApiErrorMessage(err, '请重试')}`);
    }
  };

  const applicationCount = Object.keys(applicationByResume).length;

  return (
    <Card
      className="content-card"
      title="匹配候选人"
      extra={(
        <Space>
          <Link to={`/employer/applications/${jobId}`}>
            <Button type="primary" icon={<FileTextOutlined />}>
              申请记录{applicationCount > 0 ? ` (${applicationCount})` : ''}
            </Button>
          </Link>
          <Link to="/employer/my-jobs"><Button>返回岗位列表</Button></Link>
        </Space>
      )}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="匹配推荐不等于候选人授权"
        description={(
          <>
            本页展示系统<strong>匹配推荐</strong>的候选人。仅候选人真实投递后，
            才能针对该申请运行可信度审计、发起澄清或发送面试邀请。
            MatchResult 本身不构成访问或联系授权。
            对话与状态管理请前往
            <Link to={`/employer/applications/${jobId}`}> 申请记录 </Link>
            查看。
          </>
        )}
      />

      {clarificationNotice && (
        <Alert
          type="success"
          showIcon
          closable
          style={{ marginBottom: 16 }}
          onClose={() => setClarificationNotice(null)}
          message="澄清请求已发送"
          description={(
            <Space direction="vertical" size={4}>
              <span>已生成申请记录，候选人可在「已申请岗位」中回复。</span>
              <Link to={applicationsLink(clarificationNotice.applicationId)}>
                <Button type="link" size="small" style={{ padding: 0 }}>
                  去申请记录查看对话
                </Button>
              </Link>
            </Space>
          )}
        />
      )}

      <Spin spinning={loading}>
        <List
          dataSource={candidates}
          renderItem={(item) => {
            const app = applicationByResume[item.resume_id];
            const statusCfg = app ? getStatusConfig(app.status, 'employer') : null;
            return (
              <List.Item
                extra={(
                  <Space direction="vertical" align="end">
                    <Tag color="blue">{item.score} 分</Tag>
                    {app && <Tag color={statusCfg.color}>已申请 · {statusCfg.text}</Tag>}
                    <Space wrap>
                      <Button
                        size="small"
                        icon={<EyeOutlined />}
                        disabled={!app}
                        onClick={() => viewResume(item.resume_id)}
                      >
                        查看简历
                      </Button>
                      <Button
                        size="small"
                        icon={<AuditOutlined />}
                        disabled={!app}
                        onClick={() => openAudit(item)}
                      >
                        履历审计
                      </Button>
                      <Button
                        size="small"
                        type="primary"
                        icon={<SendOutlined />}
                        disabled={!app || (app.open_claim_count || 0) > 0}
                        onClick={() => handleInvite(item.resume_id)}
                      >
                        邀请面试
                      </Button>
                    </Space>
                  </Space>
                )}
              >
                <List.Item.Meta
                  title={`${item.candidate_name} · 期望：${item.expected_title}`}
                  description={item.reason}
                />
              </List.Item>
            );
          }}
          locale={{ emptyText: '暂无匹配候选人' }}
        />
      </Spin>

      <Modal
        title="候选人简历"
        open={!!selectedResume}
        onCancel={() => setSelectedResume(null)}
        footer={null}
        width={720}
        destroyOnClose
      >
        <Spin spinning={resumeLoading}>
          {selectedResume?.parsed && (
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="姓名">
                {selectedResume.parsed.name || '匿名'}
              </Descriptions.Item>
              <Descriptions.Item label="期望职位">
                {selectedResume.parsed.expected_job_title || '未填写'}
              </Descriptions.Item>
              <Descriptions.Item label="技能" span={2}>
                <Space wrap>
                  {(selectedResume.parsed.skills || []).map((skill, idx) => (
                    <Tag color="blue" key={idx}>{skill.name}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="工作经历" span={2}>
                {(selectedResume.parsed.work_experience || []).map((exp, idx) => (
                  <div key={idx} style={{ marginBottom: 8 }}>
                    <Text strong>{exp.company} - {exp.position}</Text>
                    {exp.description && (
                      <div style={{ color: '#666' }}>{exp.description}</div>
                    )}
                  </div>
                ))}
              </Descriptions.Item>
            </Descriptions>
          )}
        </Spin>
      </Modal>

      <Drawer
        title={auditTarget ? `履历审计 · ${auditTarget.candidateName}` : '履历审计'}
        open={!!auditTarget}
        onClose={() => setAuditTarget(null)}
        width={480}
        destroyOnClose
      >
        {auditTarget && (
          <ResumeCredibilityPanel
            compact
            jobId={jobId}
            resumeId={auditTarget.resumeId}
            applicationId={auditTarget.applicationId}
            candidateName={auditTarget.candidateName}
            onClarificationSent={handleClarificationSent}
          />
        )}
      </Drawer>

      <Modal
        title="发送面试邀请"
        open={inviteModalOpen}
        onCancel={() => {
          setInviteModalOpen(false);
          form.resetFields();
        }}
        footer={null}
        destroyOnClose
      >
        <Form form={form} onFinish={sendInvitation} layout="vertical">
          <Form.Item
            name="message"
            label="邀请消息"
            rules={[{ required: true, message: '请输入邀请消息' }]}
          >
            <Input.TextArea
              rows={4}
              placeholder="您好，我们对您的简历很感兴趣，诚邀您参加面试……"
            />
          </Form.Item>
          <Form.Item name="proposed_time" label="建议面试时间（可选）">
            <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              发送邀请
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

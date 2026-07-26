import { useEffect, useState } from 'react';
import { Card, List, Input, Button, Space, Tag, message, Spin, Modal, Descriptions, Typography, Select } from 'antd';
import { SearchOutlined, EnvironmentOutlined, ClockCircleOutlined, DollarOutlined, SendOutlined, MessageOutlined } from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';

const { Text } = Typography;

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'soe', label: '国企' },
  { value: 'foreign', label: '外企' },
  { value: 'employer', label: '企业直招' },
];

function sourceTagColor(source) {
  if (source === '国企') return 'red';
  if (source === '外企') return 'blue';
  return 'default';
}

export default function BrowseJobs() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [location, setLocation] = useState('');
  const [salaryMin, setSalaryMin] = useState('');
  const [salaryMax, setSalaryMax] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [resumes, setResumes] = useState([]);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [applyModalOpen, setApplyModalOpen] = useState(false);
  const [applyingJob, setApplyingJob] = useState(null);
  const [selectedResumeId, setSelectedResumeId] = useState();
  const [coverLetter, setCoverLetter] = useState('');
  const [submittingApplication, setSubmittingApplication] = useState(false);
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [currentApplication, setCurrentApplication] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatText, setChatText] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const params = { sort_by: 'created_at' };
      if (keyword.trim()) params.keyword = keyword.trim();
      if (location.trim()) params.location = location.trim();
      if (salaryMin) params.salary_min = Number(salaryMin);
      if (salaryMax) params.salary_max = Number(salaryMax);
      if (sourceType) params.source_type = sourceType;
      const res = await api.get('/browse-jobs', { params });
      setJobs(res.data);
    } catch {
      message.error('加载岗位列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    api.get('/browse-jobs', { params: { sort_by: 'created_at' } })
      .then((res) => {
        if (!cancelled) setJobs(res.data);
      })
      .catch(() => {
        if (!cancelled) message.error('加载岗位列表失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchResumes = async () => {
    const userId = localStorage.getItem('user_id');
    if (!userId) {
      message.warning('请先登录后再申请岗位');
      return [];
    }

    setResumeLoading(true);
    try {
      const res = await api.get(`/resumes/${userId}`);
      setResumes(res.data || []);
      return res.data || [];
    } catch {
      message.error('加载简历失败，请先确认后端服务正常');
      return [];
    } finally {
      setResumeLoading(false);
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

  const openApplyModal = async (job) => {
    setApplyingJob(job);
    setApplyModalOpen(true);
    setCoverLetter('');
    setSelectedResumeId(undefined);

    const resumeList = resumes.length ? resumes : await fetchResumes();
    if (resumeList.length) {
      setSelectedResumeId(resumeList[0].id);
    }
  };

  const loadMessages = async (applicationId) => {
    setChatLoading(true);
    try {
      const res = await api.get(`/applications/${applicationId}/messages`);
      setChatMessages(res.data || []);
    } catch {
      message.error('加载对话失败');
    } finally {
      setChatLoading(false);
    }
  };

  const openChat = async (application) => {
    setCurrentApplication(application);
    setChatModalOpen(true);
    await loadMessages(application.id);
  };

  const submitApplication = async () => {
    if (!applyingJob?.id) return;
    if (!selectedResumeId) {
      message.warning('请先选择一份简历');
      return;
    }

    setSubmittingApplication(true);
    try {
      const res = await api.post('/applications', {
        job_id: applyingJob.id,
        resume_id: selectedResumeId,
        cover_letter: coverLetter,
      });
      const application = res.data.application;
      message.success(res.data.status === 'exists' ? '你已经申请过该岗位' : '申请已提交');
      setApplyModalOpen(false);
      setSelectedJob(null);
      await openChat(application);
    } catch (err) {
      message.error(`申请失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setSubmittingApplication(false);
    }
  };

  const sendChatMessage = async () => {
    const body = chatText.trim();
    if (!body || !currentApplication?.id) return;

    setSendingMessage(true);
    try {
      const res = await api.post(`/applications/${currentApplication.id}/messages`, { body });
      setChatMessages((prev) => [...prev, res.data]);
      setChatText('');
    } catch (err) {
      message.error(`发送失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setSendingMessage(false);
    }
  };

  return (
    <Card className="content-card" title="浏览所有岗位">
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          placeholder="关键字搜索"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          style={{ width: 180 }}
          prefix={<SearchOutlined />}
          onPressEnter={fetchJobs}
        />
        <Input
          placeholder="工作地点"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          style={{ width: 130 }}
          prefix={<EnvironmentOutlined />}
          onPressEnter={fetchJobs}
        />
        <Input
          placeholder="最低薪资(k)"
          value={salaryMin}
          onChange={(e) => setSalaryMin(e.target.value)}
          style={{ width: 120 }}
          type="number"
          prefix={<DollarOutlined />}
          onPressEnter={fetchJobs}
        />
        <Input
          placeholder="最高薪资(k)"
          value={salaryMax}
          onChange={(e) => setSalaryMax(e.target.value)}
          style={{ width: 120 }}
          type="number"
          prefix={<DollarOutlined />}
          onPressEnter={fetchJobs}
        />
        <Select
          placeholder="岗位来源"
          style={{ width: 130 }}
          value={sourceType || undefined}
          onChange={(v) => setSourceType(v || '')}
          options={SOURCE_OPTIONS}
          allowClear
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchJobs}>搜索</Button>
      </Space>

      <Spin spinning={loading}>
        <List
          dataSource={jobs}
          renderItem={(item) => (
            <List.Item
              className="job-list-item"
              style={{ cursor: 'pointer' }}
              onClick={() => showJobDetail(item.id)}
              extra={
                <Space direction="vertical" size={0} style={{ textAlign: 'right' }}>
                  <Text type="secondary">
                    <EnvironmentOutlined /> {item.parsed?.location || '不限'}
                  </Text>
                  <Text type="secondary">
                    <ClockCircleOutlined /> {new Date(item.created_at).toLocaleDateString()}
                  </Text>
                  <Button
                    size="small"
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      openApplyModal(item);
                    }}
                  >
                    申请岗位
                  </Button>
                </Space>
              }
            >
              <List.Item.Meta
                  title={
		    <Space>
			<span style={{ fontSize: 16 }}>{item.title}</span>
			<Tag color={sourceTagColor(item.source)}>{item.source}</Tag>
		    </Space>	
		  }
                description={
                  <Text type="secondary">
		    {item.company_name && `${item.company_name} · `}
		    {item.parsed?.salary_range ? `薪资：${item.parsed.salary_range}` : '薪资面议'}
                  </Text>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: '暂无岗位' }}
        />
      </Spin>

      {/* 岗位详情弹窗 */}
      <Modal
        title={selectedJob?.title}
        open={!!selectedJob}
        onCancel={() => setSelectedJob(null)}
        footer={[
          <Button key="close" onClick={() => setSelectedJob(null)}>
            关闭
          </Button>,
          <Button
            key="apply"
            type="primary"
            icon={<SendOutlined />}
            onClick={() => openApplyModal(selectedJob)}
          >
            申请岗位
          </Button>,
        ]}
        width={700}
        destroyOnClose
      >
        <Spin spinning={detailLoading}>
          {selectedJob?.parsed && (
            <Descriptions bordered column={2}>
              <Descriptions.Item label="工作地点">
                {selectedJob.parsed.location || '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="薪资范围">
                {selectedJob.parsed.salary_range || '面议'}
              </Descriptions.Item>
              <Descriptions.Item label="经验要求">
                {selectedJob.parsed.experience_years ? `${selectedJob.parsed.experience_years} 年` : '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="学历要求">
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
                <div
		  style={{ maxHeight: 300, overflow: 'auto', lineHeight: 1.8 }}
		  dangerouslySetInnerHTML={{
		    __html: selectedJob.parsed?.responsibilities?.join('<br/>') || ''
		  }}
		/>
	      </Descriptions.Item>
	      {selectedJob.company_name && (
		<Descriptions.Item label="发布单位">{selectedJob.company_name}</Descriptions.Item>
)}
	      {selectedJob.contact_person && (
		<Descriptions.Item label="联系人">{selectedJob.contact_person}</Descriptions.Item>
)}
	      {selectedJob.contact_info && (
		<Descriptions.Item label="联系方式">{selectedJob.contact_info}</Descriptions.Item>
)}	  
            </Descriptions>
          )}
        </Spin>
      </Modal>

      <Modal
        title={`申请岗位：${applyingJob?.title || ''}`}
        open={applyModalOpen}
        onCancel={() => setApplyModalOpen(false)}
        onOk={submitApplication}
        okText="提交申请"
        cancelText="取消"
        confirmLoading={submittingApplication}
        destroyOnClose
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <Text strong>选择投递简历</Text>
            <Select
              loading={resumeLoading}
              value={selectedResumeId}
              onChange={setSelectedResumeId}
              style={{ width: '100%', marginTop: 8 }}
              placeholder="请选择简历"
              options={resumes.map((resume, index) => ({
                value: resume.id,
                label: `简历 ${index + 1} · ${new Date(resume.uploaded_at).toLocaleString()}`,
              }))}
            />
            {!resumeLoading && !resumes.length && (
              <Text type="secondary">你还没有上传简历，请先到“上传简历”页面上传。</Text>
            )}
          </div>
          <div>
            <Text strong>给 HR 的留言</Text>
            <Input.TextArea
              rows={5}
              value={coverLetter}
              onChange={(event) => setCoverLetter(event.target.value)}
              placeholder="您好，我对这个岗位很感兴趣，我的经历和岗位要求比较匹配，希望有机会进一步沟通。"
              style={{ marginTop: 8 }}
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title={`和 HR 对话：${currentApplication?.job_title || applyingJob?.title || ''}`}
        open={chatModalOpen}
        onCancel={() => setChatModalOpen(false)}
        footer={null}
        width={680}
        destroyOnClose
      >
        <Spin spinning={chatLoading}>
          <List
            dataSource={chatMessages}
            locale={{ emptyText: '暂无消息，可以先发一条自我介绍。' }}
            style={{ maxHeight: 360, overflow: 'auto', marginBottom: 16 }}
            renderItem={(item) => (
              <List.Item style={{ justifyContent: item.is_mine ? 'flex-end' : 'flex-start' }}>
                <div
                  style={{
                    maxWidth: '72%',
                    padding: '10px 12px',
                    borderRadius: 8,
                    background: item.is_mine ? '#eef2ff' : '#f5f5f5',
                  }}
                >
                  <div style={{ whiteSpace: 'pre-wrap' }}>{item.body}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                  </Text>
                </div>
              </List.Item>
            )}
          />
        </Spin>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={chatText}
            onChange={(event) => setChatText(event.target.value)}
            onPressEnter={sendChatMessage}
            placeholder="输入想对 HR 说的话..."
            prefix={<MessageOutlined />}
          />
          <Button type="primary" loading={sendingMessage} onClick={sendChatMessage}>
            发送
          </Button>
        </Space.Compact>
      </Modal>
    </Card>
  );
}

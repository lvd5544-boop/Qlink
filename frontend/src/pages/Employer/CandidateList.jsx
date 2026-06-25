import { useEffect, useState } from 'react';
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
} from 'antd';
import {
  EyeOutlined,
  SendOutlined,
} from '@ant-design/icons';
import api from '../../api';

const { Text } = Typography;

export default function CandidateList() {
  const { jobId } = useParams();
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);

  // 简历查看
  const [selectedResume, setSelectedResume] = useState(null);
  const [resumeLoading, setResumeLoading] = useState(false);

  // 邀请面试
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteResumeId, setInviteResumeId] = useState(null);
  const [form] = Form.useForm();

  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/matches/job/${jobId}`);
      setCandidates(res.data);
    } catch {
      message.error('加载候选人失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, [jobId]);

  // 查看简历
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

  const closeResume = () => setSelectedResume(null);

  // 邀请面试
  const handleInvite = (resumeId) => {
    setInviteResumeId(resumeId);
    setInviteModalOpen(true);
  };

  const sendInvitation = async (values) => {
    try {
      await api.post('/invitations/send', {
        job_id: jobId,
        resume_id: inviteResumeId,
        message: values.message,
        proposed_time: values.proposed_time
          ? values.proposed_time.format('YYYY-MM-DD HH:mm')
          : null,
      });
      message.success('邀请已发送');
      setInviteModalOpen(false);
      form.resetFields();
    } catch (err) {
      message.error('发送失败：' + (err.response?.data?.detail || '请重试'));
    }
  };

  return (
    <Card
      className="content-card"
      title="匹配候选人"
      extra={<Link to="/employer/my-jobs"><Button>返回岗位列表</Button></Link>}
    >
      <Spin spinning={loading}>
        <List
          dataSource={candidates}
          renderItem={(item) => (
            <List.Item
              extra={
                <Space direction="vertical" align="center">
                  <Tag color="blue">{item.score} 分</Tag>
                  <Space>
                    <Button
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => viewResume(item.resume_id)}
                    >
                      查看简历
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      icon={<SendOutlined />}
                      onClick={() => handleInvite(item.resume_id)}
                    >
                      邀请面试
                    </Button>
                  </Space>
                </Space>
              }
            >
              <List.Item.Meta
                title={
                  <span>
                    {item.candidate_name} · 期望：{item.expected_title}
                  </span>
                }
                description={item.reason}
              />
            </List.Item>
          )}
          locale={{ emptyText: '暂无匹配候选人' }}
        />
      </Spin>

      {/* 简历详情弹窗 */}
      <Modal
        title="候选人简历"
        open={!!selectedResume}
        onCancel={closeResume}
        footer={null}
        width={700}
        destroyOnClose
      >
        <Spin spinning={resumeLoading}>
          {selectedResume?.parsed && (
            <Descriptions bordered column={2}>
              <Descriptions.Item label="姓名">
                {selectedResume.parsed.name || '匿名'}
              </Descriptions.Item>
              <Descriptions.Item label="期望职位">
                {selectedResume.parsed.expected_job_title || '未填写'}
              </Descriptions.Item>
              <Descriptions.Item label="学历">
                {selectedResume.parsed.education || '无'}
              </Descriptions.Item>
              <Descriptions.Item label="工作年限">
                {(selectedResume.parsed.work_experience || []).reduce(
                  (sum, exp) => sum + (exp.duration_years || 0),
                  0
                )}{' '}
                年
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
                    <Text type="secondary"> ({exp.duration_years} 年)</Text>
                    {exp.description && (
                      <div style={{ color: '#666' }}>{exp.description}</div>
                    )}
                  </div>
                ))}
              </Descriptions.Item>
              <Descriptions.Item label="期望薪资">
                {selectedResume.parsed.expected_salary || '未填写'}
              </Descriptions.Item>
              <Descriptions.Item label="期望地点">
                {selectedResume.parsed.location_preference || '不限'}
              </Descriptions.Item>
              <Descriptions.Item label="兴趣爱好">
                {selectedResume.parsed.hobbies?.join(', ') || '无'}
              </Descriptions.Item>
            </Descriptions>
          )}
        </Spin>
      </Modal>

      {/* 面试邀请弹窗 */}
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
          <Form.Item
            name="proposed_time"
            label="建议面试时间（可选）"
          >
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
            />
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
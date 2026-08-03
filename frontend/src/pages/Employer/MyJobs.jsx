import { useCallback, useEffect, useState } from 'react';
import { Card, List, Button, Tag, Space, message, Modal, Descriptions, Spin } from 'antd';
import { EditOutlined, EyeOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import api from '../../api';

export default function MyJobs() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const fetchJobs = useCallback(() => {
    setLoading(true);
    api.get('/jobs/mine')
      .then((res) => setJobs(res.data))
      .catch(() => message.error('加载岗位失败'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const timer = setTimeout(fetchJobs, 0);
    return () => clearTimeout(timer);
  }, [fetchJobs]);

  const handleView = (job) => {
    setSelectedJob(job);
    setDetailVisible(true);
  };

  const handleDelete = (jobId) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后无法恢复，确定要删除这个岗位吗？',
      onOk: async () => {
        try {
          await api.delete(`/jobs/${jobId}`);
          message.success('删除成功');
          fetchJobs();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  const closeDetail = () => {
    setDetailVisible(false);
    setSelectedJob(null);
  };

  return (
    <Card className="content-card" title="我的岗位">
      <Spin spinning={loading}>
        <List
          dataSource={jobs}
          renderItem={(item) => {
            const isDraft = item.parsed?._publication_status === 'draft';
            return (
            <List.Item
              extra={
                <Space wrap>
                  <Button icon={<EyeOutlined />} onClick={() => handleView(item)}>查看</Button>
                  <Link to={`/employer/edit-job/${item.id}`}>
                    <Button type={isDraft ? 'primary' : 'default'} icon={<EditOutlined />}>
                      {isDraft ? '继续发布' : '编辑'}
                    </Button>
                  </Link>
                  {!isDraft && (
                    <>
                      <Link to={`/employer/applications/${item.id}`}>
                        <Button type="primary" icon={<FileTextOutlined />}>申请记录</Button>
                      </Link>
                      <Link to={`/employer/candidates/${item.id}`}>
                        <Button>匹配候选人</Button>
                      </Link>
                    </>
                  )}
                  <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(item.id)}>删除</Button>
                </Space>
              }
            >
              <List.Item.Meta
                title={<Space>{item.title}<Tag color={isDraft ? 'default' : 'green'}>{isDraft ? '草稿' : '招聘中'}</Tag></Space>}
                description={
                  <span>
                    {item.parsed?.location && `地点：${item.parsed.location} · `}
                    发布时间：{new Date(item.created_at).toLocaleDateString()}
                  </span>
                }
              />
            </List.Item>
            );
          }}
          locale={{ emptyText: '暂无岗位' }}
        />
      </Spin>

      {/* 岗位详情弹窗 */}
      <Modal
        title={selectedJob?.title}
        open={detailVisible}
        onCancel={closeDetail}
        footer={null}
        width={700}
        destroyOnClose
      >
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
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {(selectedJob.parsed.responsibilities || []).map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Card>
  );
}

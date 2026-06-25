import { useEffect, useState } from 'react';
import { Card, Statistic, Row, Col, Typography } from 'antd';
import { FileTextOutlined, TeamOutlined, FileAddOutlined, FolderOpenOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../api';

const { Text } = Typography;

const QUICK_ACTIONS = [
  {
    title: '发布岗位',
    desc: '上传 JD 或粘贴描述',
    icon: <FileAddOutlined />,
    color: '#eef2ff',
    iconColor: '#4f46e5',
    path: '/employer/post-job',
  },
  {
    title: '我的岗位',
    desc: '管理已发布的职位',
    icon: <FolderOpenOutlined />,
    color: '#ecfdf5',
    iconColor: '#10b981',
    path: '/employer/my-jobs',
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState({ jobs: 0, candidates: 0 });

  useEffect(() => {
    const employerId = localStorage.getItem('user_id');
    api.get(`/jobs/${employerId}`).then((res) => {
      setStats((prev) => ({ ...prev, jobs: res.data.length }));
      const jobIds = res.data.map((j) => j.id);
      if (jobIds.length === 0) return;
      Promise.all(jobIds.map((jid) => api.get(`/matches/job/${jid}`))).then((responses) => {
        const total = responses.reduce((sum, r) => sum + r.data.length, 0);
        setStats((prev) => ({ ...prev, candidates: total }));
      });
    });
  }, []);

  return (
    <div>
      <PageHeader
        title="招聘概览"
        description="发布岗位、查看匹配候选人，高效连接优质人才"
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12}>
          <Card className="stat-card stat-card-accent">
            <Statistic title="发布岗位" value={stats.jobs} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card className="stat-card stat-card-success">
            <Statistic title="匹配候选人" value={stats.candidates} prefix={<TeamOutlined />} />
          </Card>
        </Col>
      </Row>

      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        快捷入口
      </Text>
      <Row gutter={[16, 16]}>
        {QUICK_ACTIONS.map((action) => (
          <Col xs={24} sm={12} key={action.path}>
            <Card
              className="quick-action-card"
              onClick={() => navigate(action.path)}
            >
              <div
                className="quick-action-icon"
                style={{ background: action.color, color: action.iconColor }}
              >
                {action.icon}
              </div>
              <Text strong>{action.title}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 13 }}>
                {action.desc}
              </Text>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}

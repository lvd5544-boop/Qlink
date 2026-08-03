import { useEffect, useState } from 'react';
import {
  Button, Card, Statistic, Row, Col, Typography,
} from 'antd';
import {
  FileTextOutlined, TeamOutlined, FolderOpenOutlined, SolutionOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import BillingSummaryCard from '../../components/BillingSummaryCard';
import api from '../../api';

const { Text } = Typography;

const QUICK_ACTIONS = [
  {
    title: '我的岗位',
    desc: '管理已发布的职位',
    icon: <FolderOpenOutlined />,
    color: '#eef2ff',
    iconColor: '#4f46e5',
    path: '/employer/my-jobs',
  },
  {
    title: '申请与审阅',
    desc: '查看申请、简历与澄清',
    icon: <SolutionOutlined />,
    color: '#ecfdf5',
    iconColor: '#10b981',
    path: '/employer/applications',
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState({ jobs: 0, candidates: 0 });

  useEffect(() => {
    api.get('/jobs/mine').then((res) => {
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
            <Button
              type="primary"
              block
              style={{ marginTop: 16 }}
              onClick={() => navigate('/employer/post-job')}
            >
              发布新岗位
            </Button>
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card className="stat-card stat-card-success">
            <Statistic title="匹配候选人" value={stats.candidates} prefix={<TeamOutlined />} />
            <Button
              block
              style={{ marginTop: 16 }}
              onClick={() => navigate('/employer/candidates')}
            >
              进入匹配候选人
            </Button>
          </Card>
        </Col>
      </Row>

      <BillingSummaryCard audience="organization" />

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

import { useEffect, useState, useCallback } from 'react';
import { Card, Statistic, Row, Col, Typography, Progress, Spin, Alert, List, Tag, Button } from 'antd';
import {
  FileTextOutlined,
  MessageOutlined,
  StarOutlined,
  UploadOutlined,
  SearchOutlined,
  RobotOutlined,
  MedicineBoxOutlined,
  RiseOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import api from '../../api';
import {
  notifyDashboardRefresh,
  readDashboardDeltas,
  clearDashboardDeltas,
} from '../../utils/dashboardSync';

const { Text } = Typography;

const QUICK_ACTIONS = [
  {
    title: '上传简历',
    desc: 'AI 自动解析生成画像',
    icon: <UploadOutlined />,
    color: '#eef2ff',
    iconColor: '#4f46e5',
    path: '/candidate/upload-resume',
  },
  {
    title: '浏览岗位',
    desc: '搜索全平台公开岗位',
    icon: <SearchOutlined />,
    color: '#ecfdf5',
    iconColor: '#10b981',
    path: '/candidate/browse-jobs',
  },
  {
    title: '虚拟面试',
    desc: '与 AI 面试官对话',
    icon: <RobotOutlined />,
    color: '#fff7ed',
    iconColor: '#f59e0b',
    path: '/candidate/interview',
  },
];

function DeltaBadge({ value, suffix = '' }) {
  if (value == null || value === 0) return null;
  const positive = value > 0;
  return (
    <Tag color={positive ? 'success' : 'warning'} style={{ marginLeft: 8 }}>
      <RiseOutlined /> {positive ? '+' : ''}{value}{suffix}
    </Tag>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [recentDeltas, setRecentDeltas] = useState(null);

  const userId = localStorage.getItem('user_id');

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/dashboard/candidate/${userId}`);
      setSummary(res.data);
    } catch {
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchSummary();
    setRecentDeltas(readDashboardDeltas());

    const onRefresh = () => {
      fetchSummary();
      setRecentDeltas(readDashboardDeltas());
    };
    const onFocus = () => {
      fetchSummary();
      setRecentDeltas(readDashboardDeltas());
    };

    window.addEventListener('dashboard-refresh', onRefresh);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('dashboard-refresh', onRefresh);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchSummary]);

  const indicators = summary?.indicators || {};
  const healthScore = indicators.health_score ?? summary?.health_score;
  const completenessScore = indicators.completeness_score ?? summary?.completeness_score;
  const topMatchScore = indicators.top_match_score ?? summary?.top_match_score;

  return (
    <div>
      <PageHeader
        title="工作台"
        description="体检分、完整度、匹配分三指标联动，优化简历后实时更新"
      />

      <Spin spinning={loading}>
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={8}>
            <Card className="stat-card stat-card-accent">
              <Statistic title="我的简历" value={summary?.resume_count ?? 0} prefix={<FileTextOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card className="stat-card stat-card-success">
              <Statistic title="匹配岗位" value={summary?.match_count ?? 0} prefix={<StarOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card className="stat-card stat-card-warning">
              <Statistic
                title="面试状态"
                value="待开始"
                prefix={<MessageOutlined />}
                valueStyle={{ fontSize: 20 }}
              />
            </Card>
          </Col>
        </Row>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text type="secondary">三指标联动（基于最新简历）</Text>
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchSummary}>刷新</Button>
        </div>

        {recentDeltas && (
          <Alert
            type="success"
            showIcon
            closable
            onClose={clearDashboardDeltas}
            style={{ marginBottom: 16 }}
            message="最近优化已生效"
            description={(
              <Space wrap>
                {recentDeltas.health_score_delta != null && recentDeltas.health_score_delta !== 0 && (
                  <span>体检 {recentDeltas.health_score_delta > 0 ? '+' : ''}{recentDeltas.health_score_delta}</span>
                )}
                {recentDeltas.completeness_delta != null && recentDeltas.completeness_delta !== 0 && (
                  <span>完整度 {recentDeltas.completeness_delta > 0 ? '+' : ''}{recentDeltas.completeness_delta}</span>
                )}
                {recentDeltas.score_delta != null && recentDeltas.score_delta !== 0 && (
                  <span>匹配分 {recentDeltas.score_delta > 0 ? '+' : ''}{recentDeltas.score_delta}</span>
                )}
              </Space>
            )}
          />
        )}

        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={8}>
            <Card
              className="stat-card"
              hoverable
              onClick={() => navigate('/candidate/my-resumes')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Progress
                  type="circle"
                  percent={healthScore ?? 0}
                  size={72}
                  format={() => (healthScore != null ? healthScore : '--')}
                />
                <div>
                  <Text strong><MedicineBoxOutlined /> 简历体检</Text>
                  <DeltaBadge value={recentDeltas?.health_score_delta} />
                  <br />
                  <Text type="secondary" style={{ fontSize: 13 }}>综合健康分</Text>
                </div>
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card
              className="stat-card"
              hoverable
              onClick={() => navigate('/candidate/my-resumes')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Progress
                  type="circle"
                  percent={completenessScore ?? 0}
                  size={72}
                  strokeColor="#10b981"
                  format={() => (completenessScore != null ? completenessScore : '--')}
                />
                <div>
                  <Text strong>完整度</Text>
                  <DeltaBadge value={recentDeltas?.completeness_delta} />
                  <br />
                  <Text type="secondary" style={{ fontSize: 13 }}>字段填写覆盖</Text>
                </div>
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card
              className="stat-card"
              hoverable
              onClick={() => navigate('/candidate/jobs')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Progress
                  type="circle"
                  percent={topMatchScore != null ? Math.min(topMatchScore * 10, 100) : 0}
                  size={72}
                  strokeColor="#f59e0b"
                  format={() => (topMatchScore != null ? Number(topMatchScore).toFixed(1) : '--')}
                />
                <div>
                  <Text strong>最高匹配</Text>
                  <DeltaBadge value={recentDeltas?.score_delta} />
                  <br />
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    {indicators.top_match_title || summary?.top_match_title || '暂无匹配'}
                  </Text>
                </div>
              </div>
            </Card>
          </Col>
        </Row>

        {summary?.top_matches?.length > 0 && (
          <Card
            size="small"
            title="Top 2 匹配岗位"
            style={{ marginBottom: 24 }}
            extra={(
              <Button type="link" size="small" onClick={() => navigate('/candidate/jobs')}>
                查看全部
              </Button>
            )}
          >
            <List
              size="small"
              dataSource={summary.top_matches}
              renderItem={(m, idx) => (
                <List.Item>
                  <Space>
                    <Tag color={idx === 0 ? 'gold' : 'blue'}>#{idx + 1}</Tag>
                    <Text strong>{m.job_title}</Text>
                    <Tag color="volcano">{Number(m.score).toFixed(1)} 分</Tag>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        )}

        {!summary?.latest_resume_id && !loading && (
          <Alert
            type="info"
            showIcon
            message="上传简历后，体检分、完整度与匹配分将在此联动展示"
            style={{ marginBottom: 24 }}
          />
        )}
      </Spin>

      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        快捷入口
      </Text>
      <Row gutter={[16, 16]}>
        {QUICK_ACTIONS.map((action) => (
          <Col xs={24} sm={8} key={action.path}>
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

// 供上传页等场景触发联动（导出以便复用）
export { notifyDashboardRefresh };

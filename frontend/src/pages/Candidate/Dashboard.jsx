import { useEffect, useState, useCallback } from 'react';
import { Card, Statistic, Row, Col, Typography, Progress, Spin, Alert, List, Tag, Button, Space } from 'antd';
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
  ArrowRightOutlined,
  CheckCircleFilled,
  RocketOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import BillingSummaryCard from '../../components/BillingSummaryCard';
import api from '../../api';
import { readDashboardDeltas, clearDashboardDeltas } from '../../utils/dashboardSync';

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
    const initialTimer = setTimeout(() => {
      fetchSummary();
      setRecentDeltas(readDashboardDeltas());
    }, 0);

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
      clearTimeout(initialTimer);
      window.removeEventListener('dashboard-refresh', onRefresh);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchSummary]);

  const indicators = summary?.indicators || {};
  const healthScore = indicators.health_score ?? summary?.health_score;
  const completenessScore = indicators.completeness_score ?? summary?.completeness_score;
  const topMatchScore = indicators.top_match_score ?? summary?.top_match_score;

  return (
    <div className="dashboard-page">
      <PageHeader
        title="工作台"
        description="从一个目标岗位开始，完成分析、优化和投递准备"
        extra={<span className="page-eyebrow">Evidence-led career workspace</span>}
      />

      <section className="workflow-hero" aria-labelledby="workflow-hero-title">
        <div className="workflow-hero-content">
          <div className="workflow-hero-kicker">
            <RocketOutlined /> QLink 主推 · AI 求职工作流
          </div>
          <Typography.Title id="workflow-hero-title" level={2}>
            把目标岗位，变成一份更能打的申请方案
          </Typography.Title>
          <Typography.Paragraph>
            选定岗位和简历，先看清证据、缺口与优先级，再生成由你确认的申请材料和提升行动。
          </Typography.Paragraph>
          <Space wrap size={12} className="workflow-hero-actions">
            <Button
              type="primary"
              size="large"
              icon={<RocketOutlined />}
              onClick={() => navigate('/candidate/advisor')}
            >
              开始我的求职工作流
            </Button>
            <Button
              size="large"
              onClick={() => navigate('/candidate/advisor?import=1')}
            >
              粘贴外部 JD <ArrowRightOutlined />
            </Button>
          </Space>
          <div className="workflow-trust-row" aria-label="工作流保障">
            <span><CheckCircleFilled /> 不虚构经历</span>
            <span><CheckCircleFilled /> 建议可核验</span>
            <span><CheckCircleFilled /> 你决定是否采用</span>
          </div>
        </div>
        <ol className="workflow-steps" aria-label="AI 求职工作流步骤">
          <li>
            <span>01</span>
            <div><strong>选目标岗位</strong><small>平台岗位或外部 JD</small></div>
          </li>
          <li>
            <span>02</span>
            <div><strong>对照真实履历</strong><small>找优势、缺口与优先级</small></div>
          </li>
          <li>
            <span>03</span>
            <div><strong>生成可投方案</strong><small>简历版本与下一步行动</small></div>
          </li>
        </ol>
      </section>

      <Spin spinning={loading}>
        <Row className="dashboard-stat-grid" gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={8}>
            <Card
              className="stat-card stat-card-accent"
              hoverable
              onClick={() => navigate('/candidate/my-resumes')}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  navigate('/candidate/my-resumes');
                }
              }}
              aria-label="打开我的简历"
            >
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

        <div className="section-heading-row">
          <div>
            <span className="section-kicker">Preparation signals</span>
            <Text strong className="section-title">申请准备状态</Text>
            <Text type="secondary" className="section-description">基于最新简历，帮助你决定下一步，不代表录取概率</Text>
          </div>
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchSummary}>刷新</Button>
        </div>

        {recentDeltas && (
          <Alert
            className="editorial-guidance-card editorial-guidance-card-compact"
            type="success"
            showIcon
            closable
            onClose={clearDashboardDeltas}
            style={{ marginBottom: 16 }}
            message="最近修改已更新准备建议"
            description={(
              <Space wrap>
                {recentDeltas.health_score_delta != null && recentDeltas.health_score_delta !== 0 && (
                  <span>简历体检已更新</span>
                )}
                {recentDeltas.completeness_delta != null && recentDeltas.completeness_delta !== 0 && (
                  <span>完整度已更新</span>
                )}
                {recentDeltas.score_delta != null && recentDeltas.score_delta !== 0 && (
                  <span>岗位建议已更新</span>
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
            title="优先查看的岗位"
            className="editorial-list-card"
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
                    <Tag color={idx === 0 ? 'green' : 'blue'}>{idx === 0 ? '建议先看' : '可以了解'}</Tag>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        )}

        {!summary?.latest_resume_id && !loading && (
          <Alert
            className="editorial-guidance-card editorial-guidance-card-compact"
            type="info"
            showIcon
            message="上传简历后，体检分、完整度与匹配分将在此联动展示"
            style={{ marginBottom: 24 }}
          />
        )}
      </Spin>

      <BillingSummaryCard audience="candidate" />

      <div className="section-heading-row section-heading-row-compact">
        <div>
          <span className="section-kicker">Shortcuts</span>
          <Text strong className="section-title">快捷入口</Text>
        </div>
      </div>
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

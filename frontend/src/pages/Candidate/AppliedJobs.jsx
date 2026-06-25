import { useEffect, useState } from 'react';
import {
  Card,
  List,
  Tag,
  message,
  Spin,
  Button,
  Collapse,
  Empty,
  Space,
} from 'antd';
import {
  ReloadOutlined,
  EnvironmentOutlined,
  DollarOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import api from '../../api';
import MatchEvaluationPanel from '../../components/MatchEvaluationPanel';

const STATUS_LABELS = {
  submitted: { text: '已提交', color: 'processing' },
  reviewing: { text: '审核中', color: 'warning' },
  accepted: { text: '已通过', color: 'success' },
  rejected: { text: '未通过', color: 'error' },
};

export default function AppliedJobs() {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchApplications = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await api.get('/applications/mine/evaluations');
      setApplications(res.data || []);
    } catch {
      message.error('加载已申请岗位失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchApplications();
  }, []);

  const collapseItems = applications.map((app) => {
    const status = STATUS_LABELS[app.status] || { text: app.status, color: 'default' };
    const ev = app.evaluation;

    return {
      key: app.id,
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 600, fontSize: 15 }}>{app.job_title || '未知岗位'}</span>
          <Tag color={status.color}>{status.text}</Tag>
          {ev && (
            <>
              <Tag color="volcano">{ev.match_score} 分</Tag>
              <Tag color="blue">潜力 {ev.potential_score}</Tag>
            </>
          )}
        </div>
      ),
      extra: (
        <Space onClick={(e) => e.stopPropagation()} style={{ color: '#64748b', fontSize: 13 }}>
          <EnvironmentOutlined /> {app.job_location || '不限'}
          <DollarOutlined /> {app.job_salary || '面议'}
        </Space>
      ),
      children: (
        <div>
          <div style={{ marginBottom: 12, color: '#64748b', fontSize: 13 }}>
            申请时间：{app.created_at ? new Date(app.created_at).toLocaleString() : '—'}
          </div>
          <MatchEvaluationPanel evaluation={ev} />
        </div>
      ),
    };
  });

  return (
    <Card
      className="content-card"
      title={
        <Space>
          <FileSearchOutlined />
          已申请岗位
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => fetchApplications(true)}>
          刷新评分
        </Button>
      }
    >
      <Spin spinning={loading || refreshing}>
        {applications.length === 0 ? (
          <Empty
            description="暂无申请记录"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Link to="/candidate/browse-jobs">
              <Button type="primary">去浏览岗位</Button>
            </Link>
          </Empty>
        ) : (
          <Collapse
            items={collapseItems}
            defaultActiveKey={applications[0]?.id ? [applications[0].id] : []}
            accordion={false}
          />
        )}
      </Spin>
    </Card>
  );
}

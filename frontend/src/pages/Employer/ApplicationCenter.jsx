import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Empty, Input, List, message, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { FileSearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import { getStatusConfig } from '../../constants/applicationStatus';

const { Text } = Typography;

const FILTERS = [
  { label: '全部', value: 'all' },
  { label: '待审阅', value: 'review', statuses: ['submitted', 'viewed'] },
  { label: '澄清中', value: 'clarification', statuses: ['needs_clarification', 'clarified', 'clarification_closed'] },
  { label: '已决策', value: 'decision', statuses: ['rejected', 'accepted'] },
];

export default function ApplicationCenter() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/applications/employer/all');
      setItems(res.data || []);
    } catch (err) {
      message.error(`加载申请失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const filtered = useMemo(() => {
    const selected = FILTERS.find((item) => item.value === filter);
    const keyword = query.trim().toLowerCase();
    return items.filter((item) => {
      if (selected?.statuses && !selected.statuses.includes(item.status)) return false;
      if (!keyword) return true;
      return [item.candidate_name, item.expected_title, item.job_title]
        .some((value) => String(value || '').toLowerCase().includes(keyword));
    });
  }, [filter, items, query]);

  const filterOptions = FILTERS.map((item) => ({
    value: item.value,
    label: `${item.label} (${
      item.statuses ? items.filter((app) => item.statuses.includes(app.status)).length : items.length
    })`,
  }));

  return (
    <Card
      className="content-card"
      title="申请与审阅"
      extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Text type="secondary">
          跨岗位查看所有真实申请，并进入简历材料、审计、澄清及录用决策。
        </Text>
        <Input.Search
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索候选人、期望岗位或招聘岗位"
        />
        <Segmented block value={filter} onChange={setFilter} options={filterOptions} />
        <Spin spinning={loading}>
          <List
            dataSource={filtered}
            locale={{
              emptyText: (
                <Empty
                  description={items.length ? '当前筛选下暂无申请' : '暂无申请；候选人投递后会自动出现在这里'}
                />
              ),
            }}
            renderItem={(item) => {
              const status = getStatusConfig(item.status, 'employer');
              return (
                <List.Item
                  extra={(
                    <Link to={`/employer/applications/${item.job_id}?applicationId=${item.id}`}>
                      <Button type="primary" icon={<FileSearchOutlined />}>进入审阅</Button>
                    </Link>
                  )}
                >
                  <List.Item.Meta
                    title={(
                      <Space wrap>
                        <span>{item.candidate_name}</span>
                        <Tag color={status.color}>{status.text}</Tag>
                        {(item.answered_unreviewed_count || 0) > 0 && <Tag color="cyan">有新回复</Tag>}
                      </Space>
                    )}
                    description={(
                      <Space direction="vertical" size={2}>
                        <Text>申请岗位：{item.job_title || '未命名岗位'}</Text>
                        <Text type="secondary">
                          候选人期望：{item.expected_title || '未填写'} ·
                          {' '}投递时间：{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
                        </Text>
                      </Space>
                    )}
                  />
                </List.Item>
              );
            }}
          />
        </Spin>
      </Space>
    </Card>
  );
}

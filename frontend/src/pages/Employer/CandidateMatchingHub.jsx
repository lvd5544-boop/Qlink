import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Empty, List, message, Space, Spin, Tag, Typography,
} from 'antd';
import { FileAddOutlined, TeamOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';

const { Text } = Typography;

export default function CandidateMatchingHub() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/jobs/mine')
      .then((res) => setJobs(res.data || []))
      .catch((err) => message.error(`加载岗位失败：${getApiErrorMessage(err, '请重试')}`))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Card
      className="content-card"
      title="匹配候选人"
      extra={(
        <Link to="/employer/post-job">
          <Button type="primary" icon={<FileAddOutlined />}>发布新岗位</Button>
        </Link>
      )}
    >
      <Alert
        type="info"
        showIcon
        message="选择一个岗位，进入该岗位的匹配候选人页面。"
        description="候选人匹配、投递申请、履历审计和澄清均按岗位隔离。"
        style={{ marginBottom: 16 }}
      />
      <Spin spinning={loading}>
        <List
          dataSource={jobs}
          locale={{
            emptyText: (
              <Empty description="请先发布岗位，再查看匹配候选人">
                <Link to="/employer/post-job"><Button type="primary">发布岗位</Button></Link>
              </Empty>
            ),
          }}
          renderItem={(job) => (
            <List.Item
              extra={(
                <Link to={`/employer/candidates/${job.id}`}>
                  <Button type="primary" icon={<TeamOutlined />}>查看匹配候选人</Button>
                </Link>
              )}
            >
              <List.Item.Meta
                title={(
                  <Space wrap>
                    <span>{job.title}</span>
                    {job.parsed?.location && <Tag>{job.parsed.location}</Tag>}
                  </Space>
                )}
                description={(
                  <Text type="secondary">
                    发布时间：{job.created_at ? new Date(job.created_at).toLocaleDateString() : '—'}
                  </Text>
                )}
              />
            </List.Item>
          )}
        />
      </Spin>
    </Card>
  );
}

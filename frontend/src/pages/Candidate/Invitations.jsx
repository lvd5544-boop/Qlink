import { useEffect, useState } from 'react';
import { Card, List, Tag, Button, message, Empty } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import api from '../../api';

export default function Invitations() {
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchInvitations = async () => {
    try {
      const res = await api.get('/invitations/received');
      setInvitations(res.data);
    } catch {
      message.error('加载邀请失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchInvitations(); }, []);

  const handleAccept = async (id) => {
    try {
      await api.put(`/invitations/${id}/accept`);
      message.success('已接受邀请，招聘方将收到通知');
      fetchInvitations();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDecline = async (id) => {
    try {
      await api.put(`/invitations/${id}/decline`);
      message.success('已拒绝邀请');
      fetchInvitations();
    } catch {
      message.error('操作失败');
    }
  };

  return (
    <Card className="content-card" title="面试邀请">
      <List
        dataSource={invitations}
        loading={loading}
        locale={{ emptyText: <Empty description="暂无面试邀请" /> }}
        renderItem={(item) => (
          <List.Item
            extra={
              item.status === 'pending' ? (
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleAccept(item.id)}>接受</Button>
                  <Button danger icon={<CloseCircleOutlined />} onClick={() => handleDecline(item.id)}>拒绝</Button>
                </div>
              ) : (
                <Tag color={item.status === 'accepted' ? 'green' : 'red'}>
                  {item.status === 'accepted' ? '已接受' : '已拒绝'}
                </Tag>
              )
            }
          >
            <List.Item.Meta
              title={<span>岗位：{item.job_title || '未知岗位'}</span>}
              description={
                <div>
                  {item.message && <p>消息：{item.message}</p>}
                  {item.proposed_time && <p>建议时间：{item.proposed_time}</p>}
                  <p>发送时间：{new Date(item.created_at).toLocaleString()}</p>
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
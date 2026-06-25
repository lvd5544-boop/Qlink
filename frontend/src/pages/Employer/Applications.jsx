import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Button, Card, Input, List, message, Space, Spin, Tag, Typography } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import api from '../../api';

const { Text } = Typography;

export default function Applications() {
  const { jobId } = useParams();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentApplication, setCurrentApplication] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);

  const fetchApplications = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/applications/job/${jobId}`);
      setApplications(res.data || []);
    } catch (err) {
      message.error('加载申请记录失败：' + (err.response?.data?.detail || '请重试'));
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async (application) => {
    setCurrentApplication(application);
    setMessagesLoading(true);
    try {
      const res = await api.get(`/applications/${application.id}/messages`);
      setMessages(res.data || []);
    } catch {
      message.error('加载对话失败');
    } finally {
      setMessagesLoading(false);
    }
  };

  const sendMessage = async () => {
    const body = messageText.trim();
    if (!body || !currentApplication?.id) return;

    setSending(true);
    try {
      const res = await api.post(`/applications/${currentApplication.id}/messages`, { body });
      setMessages((prev) => [...prev, res.data]);
      setMessageText('');
    } catch (err) {
      message.error('发送失败：' + (err.response?.data?.detail || '请重试'));
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    fetchApplications();
  }, [jobId]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        className="content-card"
        title="岗位申请记录"
        extra={<Link to="/employer/my-jobs"><Button>返回岗位列表</Button></Link>}
      >
        <Spin spinning={loading}>
          <List
            dataSource={applications}
            locale={{ emptyText: '暂无主动申请' }}
            renderItem={(item) => (
              <List.Item
                extra={
                  <Button
                    type="primary"
                    icon={<MessageOutlined />}
                    onClick={() => loadMessages(item)}
                  >
                    对话
                  </Button>
                }
              >
                <List.Item.Meta
                  title={`${item.candidate_name} · ${item.expected_title}`}
                  description={
                    <Space direction="vertical" size={4}>
                      <Text type="secondary">
                        申请时间：{item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                      </Text>
                      {item.cover_letter && <Text>{item.cover_letter}</Text>}
                    </Space>
                  }
                />
                <Tag color="blue">已申请</Tag>
              </List.Item>
            )}
          />
        </Spin>
      </Card>

      {currentApplication && (
        <Card className="content-card" title={`和 ${currentApplication.candidate_name} 对话`}>
          <Spin spinning={messagesLoading}>
            <List
              dataSource={messages}
              locale={{ emptyText: '暂无消息' }}
              style={{ maxHeight: 360, overflow: 'auto', marginBottom: 16 }}
              renderItem={(item) => (
                <List.Item style={{ justifyContent: item.is_mine ? 'flex-end' : 'flex-start' }}>
                  <div
                    style={{
                      maxWidth: '72%',
                      padding: '10px 12px',
                      borderRadius: 8,
                      background: item.is_mine ? '#eef2ff' : '#f5f5f5',
                    }}
                  >
                    <div style={{ whiteSpace: 'pre-wrap' }}>{item.body}</div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                    </Text>
                  </div>
                </List.Item>
              )}
            />
          </Spin>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              onPressEnter={sendMessage}
              placeholder="回复候选人..."
              prefix={<MessageOutlined />}
            />
            <Button type="primary" loading={sending} onClick={sendMessage}>
              发送
            </Button>
          </Space.Compact>
        </Card>
      )}
    </Space>
  );
}

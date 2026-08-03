import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button, Descriptions, List, Modal, Space, Tag, Typography, message,
} from 'antd';
import { AimOutlined, EyeOutlined, StarOutlined } from '@ant-design/icons';
import api from '../api';
import { decodeHtmlEntities } from '../utils/text';

const { Paragraph, Text } = Typography;

const textList = (value) => {
  if (!value) return '未说明';
  if (Array.isArray(value)) {
    const rows = value.map((item) => (
      typeof item === 'object' ? (item.name || item.title || JSON.stringify(item)) : String(item)
    )).filter(Boolean);
    return rows.length ? rows.join('、') : '未说明';
  }
  return String(value);
};

export default function TopJobMatches({
  matches = [],
  loading = false,
  targetJobId = null,
  onTargetChange,
}) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const openDetail = async (match) => {
    setDetailLoading(true);
    try {
      const response = await api.get(`/job/${match.job_id}`);
      setDetail({ ...response.data, matchScore: match.score });
    } catch {
      message.error('岗位详情暂时无法加载，请稍后再试');
    } finally {
      setDetailLoading(false);
    }
  };

  const selectTarget = (match) => {
    onTargetChange?.(match);
    message.success(`已将“${decodeHtmlEntities(match.job_title)}”设为优化目标`);
  };

  return (
    <>
      <Space style={{ marginBottom: 4 }}>
        <StarOutlined />
        <Text strong>最匹配的 3 个岗位</Text>
      </Space>
      {matches.length === 0 ? (
        <Space direction="vertical" size={6}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            还没有匹配结果。岗位池为空或后台仍在计算时，可先手动选择真实岗位。
          </Text>
          <Button size="small" type="link" onClick={() => navigate('/candidate/browse-jobs')}>
            去岗位池抓取与选择
          </Button>
        </Space>
      ) : (
        <List
          loading={loading}
          size="small"
          dataSource={matches}
          renderItem={(match, index) => {
            const selected = String(targetJobId) === String(match.job_id);
            return (
              <List.Item
                style={{
                  padding: '8px 0',
                  cursor: 'pointer',
                  background: selected ? '#f0f7ff' : undefined,
                  borderRadius: 6,
                }}
                onClick={() => openDetail(match)}
                actions={[
                  <Button
                    key="detail"
                    type="link"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      openDetail(match);
                    }}
                  >
                    查看详情
                  </Button>,
                  <Button
                    key="target"
                    type={selected ? 'default' : 'link'}
                    size="small"
                    icon={<AimOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectTarget(match);
                    }}
                  >
                    {selected ? '当前优化目标' : '用这个岗位优化'}
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<Tag color={index === 0 ? 'gold' : 'blue'}>#{index + 1}</Tag>}
                  title={<Text>{decodeHtmlEntities(match.job_title)}</Text>}
                  description={`匹配参考分 ${Number(match.score).toFixed(1)}`}
                />
              </List.Item>
            );
          }}
        />
      )}

      <Modal
        title={decodeHtmlEntities(detail?.title) || '岗位详情'}
        open={Boolean(detail)}
        loading={detailLoading}
        width={760}
        onCancel={() => setDetail(null)}
        footer={[
          <Button key="close" onClick={() => setDetail(null)}>关闭</Button>,
          <Button
            key="target"
            type="primary"
            icon={<AimOutlined />}
            onClick={() => {
              const match = matches.find((item) => String(item.job_id) === String(detail?.id));
              if (match) selectTarget(match);
              setDetail(null);
            }}
          >
            设为优化目标并返回工作台
          </Button>,
        ]}
      >
        {detail && (
          <>
            <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label="公司">
                {detail.parsed?.company_name || detail.company_name || '未说明'}
              </Descriptions.Item>
              <Descriptions.Item label="工作地点">
                {detail.parsed?.location || '未说明'}
              </Descriptions.Item>
              <Descriptions.Item label="薪资范围">
                {detail.parsed?.salary_range || '未说明'}
              </Descriptions.Item>
              <Descriptions.Item label="经验要求">
                {detail.parsed?.experience_years != null
                  ? `${detail.parsed.experience_years} 年`
                  : '未说明'}
              </Descriptions.Item>
              <Descriptions.Item label="核心技能" span={2}>
                {textList(detail.parsed?.required_skills)}
              </Descriptions.Item>
            </Descriptions>
            <Paragraph style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
              {detail.parsed?.description || detail.raw_text || '该岗位暂未提供更多描述。'}
            </Paragraph>
          </>
        )}
      </Modal>
    </>
  );
}

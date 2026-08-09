import { useState } from 'react';
import {
  Alert, Button, Card, Collapse, Empty, List, Space, Tag, Typography, message,
} from 'antd';
import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';
import {
  buildOpportunityPreparation,
  opportunityPreparationAsText,
} from './opportunityPreparation';

const { Paragraph, Text } = Typography;

function TextList({ items, emptyText, renderItem }) {
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />;
  return <List size="small" dataSource={items} renderItem={renderItem || ((item) => <List.Item>{item}</List.Item>)} />;
}

export default function OpportunityPreparationCard({ resumeId, jobId, diagnostic }) {
  const navigate = useNavigate();
  const [preparation, setPreparation] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const [claimsResponse, profileResponse] = await Promise.all([
        api.get(`/resumes/${resumeId}/claims`),
        api.get(`/advisor/jobs/${jobId}/profile`),
      ]);
      const profile = profileResponse.data || {};
      setPreparation(buildOpportunityPreparation({
        jobTitle: diagnostic?.job_title || profile.job?.title,
        requirements: profile.layers?.target_role?.requirements || [],
        claims: claimsResponse.data?.claims || [],
        diagnostic,
      }));
    } catch (error) {
      message.error(getApiErrorMessage(error, '机会准备卡生成失败'));
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!preparation) return;
    const blob = new Blob([opportunityPreparationAsText(preparation)], { type: 'text/plain;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = `${preparation.jobTitle}-机会准备卡.txt`;
    anchor.click();
    URL.revokeObjectURL(href);
  };

  const startInterview = () => {
    const params = new URLSearchParams({
      channel: 'structured',
      mode: 'target_gap',
      resumeId: String(resumeId),
      jobId: String(jobId),
      jobTitle: preparation?.jobTitle || diagnostic?.job_title || '目标岗位',
    });
    navigate(`/candidate/interview?${params.toString()}`);
  };

  const sections = preparation ? [
    {
      key: 'available',
      label: `现在可用 · ${preparation.availableNow.length}/3`,
      children: (
        <TextList
          items={preparation.availableNow}
          emptyText="暂无已确认或有证据支持的经历"
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={2}>
                <Text>{item.text}</Text>
                <Space wrap>
                  {item.source && <Tag>{item.source}</Tag>}
                  {item.evidenceState === 'supported_by_user_evidence' && <Tag color="green">有用户证据</Tag>}
                </Space>
              </Space>
            </List.Item>
          )}
        />
      ),
    },
    {
      key: 'stories',
      label: `面试故事 · ${preparation.interviewStories.length}/2`,
      children: (
        <TextList
          items={preparation.interviewStories}
          emptyText="确认一条真实经历后再生成故事提纲"
          renderItem={(story) => (
            <List.Item>
              <Space direction="vertical" size={4}>
                <Text strong>{story.anchor}</Text>
                {story.fields.map((field) => <Text key={field} type="secondary">{field}</Text>)}
              </Space>
            </List.Item>
          )}
        />
      ),
    },
    {
      key: 'clarify',
      label: `待说清 · ${preparation.clarifyingQuestions.length}/3`,
      children: <TextList items={preparation.clarifyingQuestions} emptyText="当前没有需要追问的事项" />,
    },
    {
      key: 'action',
      label: '一个行动 · 0–1',
      children: preparation.developmentAction ? (
        <Space direction="vertical" size={4}>
          <Text strong>{preparation.developmentAction.title}</Text>
          <Text type="secondary">{preparation.developmentAction.detail}</Text>
        </Space>
      ) : <Text type="secondary">当前没有经用户确认的发展行动。</Text>,
    },
    {
      key: 'unresolved',
      label: `未解决要求 · ${preparation.unresolvedRequirements.length}/3`,
      children: <TextList items={preparation.unresolvedRequirements} emptyText="当前没有未解决要求" />,
    },
  ] : [];

  return (
    <Card title="本次机会准备卡" style={{ marginTop: 12 }}>
      <Alert
        type="info"
        showIcon
        message="只整理已有事实，不把岗位要求改写成你的经历"
        description="五个短栏目直接服务申请和面试；证据冲突项不会进入可用素材。"
        style={{ marginBottom: 12 }}
      />
      {!preparation ? (
        <Button type="primary" loading={loading} onClick={generate}>生成机会准备卡</Button>
      ) : (
        <>
          <Paragraph type="secondary">目标岗位：{preparation.jobTitle}</Paragraph>
          <Collapse defaultActiveKey={['available', 'clarify']} items={sections} />
          <Space wrap style={{ marginTop: 12 }}>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={startInterview}>
              用这批真实素材开始针对性面试
            </Button>
            <Button icon={<DownloadOutlined />} onClick={download}>下载 TXT（次要）</Button>
            <Button loading={loading} onClick={generate}>重新整理</Button>
          </Space>
        </>
      )}
    </Card>
  );
}

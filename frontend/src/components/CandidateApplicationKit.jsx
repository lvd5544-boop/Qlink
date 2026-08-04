import { useState } from 'react';
import {
  Alert, Button, Card, Collapse, List, Space, Tag, Typography, message,
} from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';

const { Paragraph, Text } = Typography;

function buildText({ jobTitle, requirements, claims }) {
  const lines = [
    `目标岗位：${jobTitle || '未命名岗位'}`,
    '',
    '一、岗位重点（来自目标 JD）',
    ...requirements.map((item) => `- ${item.text}`),
    '',
    '二、可使用的履历素材（来自当前简历；请在使用前再次核对）',
    ...claims.map((claim) => `- ${claim.current_text}`),
    '',
    '三、求职信素材结构',
    '- 为什么申请：结合岗位重点，用自己的真实动机补充。',
    ...claims.slice(0, 3).map((claim) => `- 可引用经历：${claim.current_text}`),
    '- 结尾：说明你希望进一步交流的岗位问题，不承诺未经证实的能力。',
    '',
    '四、面试故事提纲（STAR）',
    ...claims.slice(0, 3).flatMap((claim, index) => [
      `${index + 1}. 素材：${claim.current_text}`,
      '   情境：当时的背景和约束是什么？',
      '   任务：你具体负责什么？',
      '   行动：你亲自采取了哪些行动，为什么？',
      '   结果：有哪些可核对的结果或证据？',
    ]),
    '',
    '说明：本文件只整理你当前简历和目标 JD 中已有的文字，不代表企业确认，也不补写未知事实。',
  ];
  return lines.join('\n');
}

export default function CandidateApplicationKit({ resumeId, jobId, diagnostic }) {
  const [kit, setKit] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const [claimsResponse, profileResponse] = await Promise.all([
        api.get(`/resumes/${resumeId}/claims`),
        api.get(`/advisor/jobs/${jobId}/profile`),
      ]);
      const allClaims = claimsResponse.data?.claims || [];
      const claims = allClaims
        .filter((claim) => claim.current_text && claim.evidence_state !== 'conflict_detected')
        .sort((left, right) => {
          const rank = (claim) => (
            claim.evidence_state === 'supported_by_user_evidence' ? 2
              : claim.confirmation_state === 'user_confirmed' ? 1 : 0
          );
          return rank(right) - rank(left);
        })
        .slice(0, 6);
      const requirements = (profileResponse.data?.layers?.target_role?.requirements || []).slice(0, 5);
      setKit({
        jobTitle: diagnostic?.job_title || profileResponse.data?.job?.title,
        requirements,
        claims,
      });
      if (!claims.length) message.warning('当前没有可安全整理的履历素材，请先补充并同步真实经历');
    } catch (error) {
      message.error(getApiErrorMessage(error, '申请素材包生成失败'));
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!kit) return;
    const blob = new Blob([buildText(kit)], { type: 'text/plain;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = `${kit.jobTitle || '目标岗位'}-申请素材包.txt`;
    anchor.click();
    URL.revokeObjectURL(href);
  };

  return (
    <Card title="当前可用申请素材包" style={{ marginTop: 12 }}>
      <Alert
        type="info"
        showIcon
        message="只整理已有事实，不把岗位要求改写成你的经历"
        description="包含岗位重点、简历素材、求职信结构和 STAR 面试提纲；证据冲突项不会导出。"
        style={{ marginBottom: 12 }}
      />
      <Button type="primary" loading={loading} onClick={generate}>
        生成有依据的申请素材包
      </Button>
      {kit && (
        <>
          <Collapse
            style={{ marginTop: 12 }}
            items={[
              {
                key: 'requirements',
                label: `岗位重点 ${kit.requirements.length} 项`,
                children: <List size="small" dataSource={kit.requirements} renderItem={(item) => <List.Item>{item.text}</List.Item>} />,
              },
              {
                key: 'claims',
                label: `可使用履历素材 ${kit.claims.length} 条`,
                children: (
                  <List
                    size="small"
                    dataSource={kit.claims}
                    locale={{ emptyText: '请先在履历记录中补充真实经历' }}
                    renderItem={(claim) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Paragraph style={{ margin: 0 }}>{claim.current_text}</Paragraph>
                          <Space wrap>
                            <Tag>{claim.source_locator}</Tag>
                            {claim.evidence_state === 'supported_by_user_evidence' && <Tag color="green">有用户证据</Tag>}
                            {claim.confirmation_state === 'user_confirmed' && <Tag color="blue">内容已确认</Tag>}
                          </Space>
                        </Space>
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: 'outline',
                label: '求职信与面试故事结构',
                children: (
                  <Space direction="vertical">
                    <Text>求职信：真实动机 → 最相关经历 → 与岗位要求的连接 → 希望进一步交流的问题。</Text>
                    <Text>面试：对每条经历补齐情境、任务、本人行动、结果与可核对证据。</Text>
                  </Space>
                ),
              },
            ]}
          />
          <Button icon={<DownloadOutlined />} style={{ marginTop: 12 }} disabled={!kit.claims.length} onClick={download}>
            下载 TXT 素材包
          </Button>
        </>
      )}
    </Card>
  );
}

import { Tag, Typography } from 'antd';

const { Text } = Typography;

function bubbleBackground(messageKind, isMine) {
  if (messageKind === 'clarification_request') return '#fff7ed';
  if (messageKind === 'clarification_response') return '#ecfdf5';
  if (messageKind === 'interview_invite') return '#eff6ff';
  if (messageKind === 'interview_summary') return '#f5f3ff';
  return isMine ? '#eef2ff' : '#f5f5f5';
}

/**
 * 申请沟通消息气泡（普通消息 / 澄清 / 面试邀请 / AI 纪要）
 */
export default function ApplicationMessageBubble({
  item,
  maxWidth = '78%',
  highlight = false,
  bodyFontSize,
}) {
  return (
    <div
      style={{
        maxWidth,
        padding: '10px 12px',
        borderRadius: 8,
        background: bubbleBackground(item.message_kind, item.is_mine),
        outline: highlight ? '2px solid #06b6d4' : undefined,
      }}
    >
      {item.message_kind === 'clarification_request' && (
        <Tag color="orange" style={{ marginBottom: 4 }}>澄清请求</Tag>
      )}
      {item.message_kind === 'clarification_response' && (
        <Tag color="green" style={{ marginBottom: 4 }}>澄清回复</Tag>
      )}
      {item.message_kind === 'interview_invite' && (
        <Tag color="blue" style={{ marginBottom: 4 }}>面试邀请</Tag>
      )}
      {item.message_kind === 'interview_summary' && (
        <Tag color="purple" style={{ marginBottom: 4 }}>AI 面试纪要</Tag>
      )}
      <div style={{ whiteSpace: 'pre-wrap', fontSize: bodyFontSize }}>{item.body}</div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
      </Text>
    </div>
  );
}

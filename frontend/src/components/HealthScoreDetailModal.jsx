import { Modal, Typography, Tag } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

function DetailStrip({ type, title, detail }) {
  const isStrength = type === 'strength';
  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        padding: '10px 12px',
        marginBottom: 8,
        borderRadius: 8,
        background: isStrength ? '#f0fdf4' : '#fef2f2',
        borderLeft: `4px solid ${isStrength ? '#10b981' : '#ef4444'}`,
      }}
    >
      {isStrength ? (
        <CheckCircleOutlined style={{ color: '#10b981', marginTop: 3 }} />
      ) : (
        <CloseCircleOutlined style={{ color: '#ef4444', marginTop: 3 }} />
      )}
      <div>
        <Text strong style={{ color: isStrength ? '#065f46' : '#991b1b' }}>{title}</Text>
        <Paragraph style={{ margin: '2px 0 0', fontSize: 13, color: '#64748b' }}>
          {detail}
        </Paragraph>
      </div>
    </div>
  );
}

export default function HealthScoreDetailModal({ open, onClose, title, detail }) {
  if (!detail) return null;

  const strengths = detail.strengths || [];
  const weaknesses = detail.weaknesses || [];

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
    >
      <div style={{ marginBottom: 16 }}>
        <Tag color="blue" style={{ fontSize: 14, padding: '4px 10px' }}>
          得分 {detail.score ?? '--'}
        </Tag>
        {detail.formula && (
          <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>
            {detail.formula}
          </Text>
        )}
        {detail.summary && (
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
            {detail.summary}
          </Paragraph>
        )}
      </div>

      {strengths.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            <CheckCircleOutlined style={{ color: '#10b981', marginRight: 6 }} />
            优势
          </Text>
          {strengths.map((item, idx) => (
            <DetailStrip
              key={`s-${idx}`}
              type="strength"
              title={item.title}
              detail={item.detail}
            />
          ))}
        </div>
      )}

      {weaknesses.length > 0 && (
        <div>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            <CloseCircleOutlined style={{ color: '#ef4444', marginRight: 6 }} />
            不足
          </Text>
          {weaknesses.map((item, idx) => (
            <DetailStrip
              key={`w-${idx}`}
              type="weakness"
              title={item.title}
              detail={item.detail}
            />
          ))}
        </div>
      )}

      {strengths.length === 0 && weaknesses.length === 0 && (
        <Text type="secondary">暂无明细，请重新体检后查看</Text>
      )}
    </Modal>
  );
}

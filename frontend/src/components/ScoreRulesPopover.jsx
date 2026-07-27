import { Popover, Tag, Typography } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { getCurrentScoreRules, getPotentialScoreRules } from '../constants/matchScoringRules';

const { Text, Paragraph } = Typography;

function CurrentRulesContent({ version }) {
  const rules = getCurrentScoreRules(version);
  return (
    <div style={{ maxWidth: 360 }}>
      <Text strong style={{ fontSize: 14 }}>{rules.title}</Text>
      <Paragraph style={{ margin: '8px 0', fontSize: 13 }}>{rules.intro}</Paragraph>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
        {rules.criteria.map((c) => (
          <li key={c.label}>
            <Text strong>{c.label}</Text>
            <Text type="secondary">（约 {c.pct}%）</Text>
            <div style={{ color: '#666', marginBottom: 4 }}>{c.desc}</div>
          </li>
        ))}
      </ul>
      <Paragraph type="secondary" style={{ margin: '10px 0 0', fontSize: 12 }}>
        {rules.disclaimer}
      </Paragraph>
    </div>
  );
}

function PotentialRulesContent() {
  const rules = getPotentialScoreRules();
  return (
    <div style={{ maxWidth: 340 }}>
      <Text strong style={{ fontSize: 14 }}>{rules.title}</Text>
      <Paragraph style={{ margin: '8px 0', fontSize: 13 }}>{rules.intro}</Paragraph>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
        {rules.points.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
      <Paragraph style={{ margin: '8px 0 0', fontSize: 13 }}>{rules.note}</Paragraph>
      <Paragraph type="secondary" style={{ margin: '10px 0 0', fontSize: 12 }}>
        {rules.disclaimer}
      </Paragraph>
    </div>
  );
}

export function ClickableScoreTag({ type, score, version = 2, color, style }) {
  const isPotential = type === 'potential';
  const content = isPotential
    ? <PotentialRulesContent />
    : <CurrentRulesContent version={version} />;

  return (
    <Popover content={content} trigger="click" placement="bottom">
      <Tag
        color={color}
        style={{
          ...style,
          cursor: 'pointer',
          userSelect: 'none',
        }}
        icon={<InfoCircleOutlined />}
      >
        {isPotential ? `可提升空间 ${score} 分` : `当前 ${score} 分`}
      </Tag>
    </Popover>
  );
}

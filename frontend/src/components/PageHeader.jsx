import { Typography } from 'antd';

const { Title, Paragraph } = Typography;

export default function PageHeader({ title, description, extra }) {
  return (
    <div
      className="page-header"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: 12,
      }}
    >
      <div style={{ flex: 1, minWidth: 200 }}>
        <Title level={4} className="page-header-title">
          {title}
        </Title>
        {description && (
          <Paragraph className="page-header-desc">{description}</Paragraph>
        )}
      </div>
      {extra}
    </div>
  );
}

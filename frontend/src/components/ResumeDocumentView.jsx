import { Tag, Space, Typography, Divider } from 'antd';

const { Text, Title, Paragraph } = Typography;

/**
 * 解析后的简历文档视图（便于对照原文与建议）。
 */
export default function ResumeDocumentView({ parsed, highlightSections = [] }) {
  if (!parsed) return null;

  const highlightSet = new Set(highlightSections);

  const sectionStyle = (key) => (
    highlightSet.has(key)
      ? { background: '#fffbeb', padding: 8, borderRadius: 8, border: '1px dashed #f59e0b' }
      : {}
  );

  return (
    <div style={{ fontSize: 14, lineHeight: 1.7, color: '#334155' }}>
      <Title level={5} style={{ marginTop: 0 }}>
        {parsed.name || '未命名'}
      </Title>
      <Text type="secondary">
        {parsed.expected_job_title || '期望职位未填'}
        {parsed.location_preference ? ` · ${parsed.location_preference}` : ''}
      </Text>

      <Divider style={{ margin: '12px 0' }} />

      <div style={sectionStyle('basic')}>
        <Text strong>联系方式</Text>
        <div>{parsed.email || '—'} · {parsed.phone || '—'}</div>
      </div>

      {parsed.summary && (
        <div style={{ marginTop: 12, ...sectionStyle('summary') }}>
          <Text strong>个人简介</Text>
          <Paragraph style={{ marginBottom: 0 }}>{parsed.summary}</Paragraph>
        </div>
      )}

      {(parsed.skills || []).length > 0 && (
        <div style={{ marginTop: 12, ...sectionStyle('skills') }}>
          <Text strong>技能</Text>
          <div style={{ marginTop: 6 }}>
            <Space wrap>
              {parsed.skills.map((s, i) => (
                <Tag key={i} color="blue">{s.name}</Tag>
              ))}
            </Space>
          </div>
        </div>
      )}

      {(parsed.work_experience || []).length > 0 && (
        <div style={{ marginTop: 12, ...sectionStyle('work_experience') }}>
          <Text strong>工作经历</Text>
          {(parsed.work_experience || []).map((exp, idx) => (
            <div
              key={idx}
              style={{
                marginTop: 8,
                padding: 8,
                borderLeft: '3px solid #e2e8f0',
                ...(highlightSet.has(`work_${idx}`) ? { background: '#fffbeb' } : {}),
              }}
            >
              <Text strong>{exp.company}</Text> · {exp.position}
              {exp.duration_years ? `（${exp.duration_years} 年）` : ''}
              {exp.description && (
                <Paragraph style={{ margin: '4px 0 0', color: '#64748b' }}>
                  {exp.description}
                </Paragraph>
              )}
            </div>
          ))}
        </div>
      )}

      {(parsed.soft_skills || []).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Text strong>软实力</Text>
          <div style={{ marginTop: 6 }}>
            <Space wrap>
              {parsed.soft_skills.map((s, i) => (
                <Tag key={i} color="purple">{s}</Tag>
              ))}
            </Space>
          </div>
        </div>
      )}

      {(parsed.projects || []).length > 0 && (
        <div style={{ marginTop: 12, ...sectionStyle('projects') }}>
          <Text strong>项目经历</Text>
          {(parsed.projects || []).map((proj, idx) => (
            <div
              key={idx}
              style={{
                marginTop: 8,
                padding: 8,
                borderLeft: '3px solid #93c5fd',
                ...(highlightSet.has(`project_${idx}`) ? { background: '#fffbeb' } : {}),
              }}
            >
              <Text strong>{proj.name}</Text>
              {proj.role ? ` · ${proj.role}` : ''}
              {proj.duration ? `（${proj.duration}）` : ''}
              {proj.description && (
                <Paragraph style={{ margin: '4px 0 0', color: '#64748b' }}>
                  {proj.description}
                </Paragraph>
              )}
            </div>
          ))}
        </div>
      )}

      {(parsed.education || parsed.school || parsed.degree) && (
        <div style={{ marginTop: 12, ...sectionStyle('education') }}>
          <Text strong>教育背景</Text>
          <div>
            {parsed.school || ''} {parsed.education || ''} {parsed.degree || ''}
            {parsed.school_tier ? ` · ${parsed.school_tier}` : ''}
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Col, Divider, Input, List, Row, Select, Space, Spin, Tag, Typography,
} from 'antd';
import { FileSearchOutlined, RobotOutlined } from '@ant-design/icons';
import api from '../api';
import SuggestionDiffCard from './SuggestionDiffCard';

const { Text, Paragraph, Title } = Typography;

const ROLE_FAMILIES = [
  { value: 'general', label: '综合' },
  { value: 'engineering', label: '技术/研发' },
  { value: 'product', label: '产品' },
  { value: 'data', label: '数据' },
  { value: 'management', label: '管理' },
  { value: 'sales', label: '销售/市场' },
  { value: 'finance', label: '财务/金融' },
];

export default function ResumeCoachPanel({
  resumeId,
  defaultJobTitle = '',
  onApplySuggestion,
  onDismissSuggestion,
  onSuggestionsUpdated,
  applyingId = null,
}) {
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState(null);
  const [roleFamily, setRoleFamily] = useState('engineering');
  const [targetJobTitle, setTargetJobTitle] = useState(defaultJobTitle);
  const [loading, setLoading] = useState(false);
  const [coachResult, setCoachResult] = useState(null);
  const [coachSuggestions, setCoachSuggestions] = useState([]);

  useEffect(() => {
    api.get('/analytics/companies').then((res) => setCompanies(res.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    setTargetJobTitle(defaultJobTitle || '');
    setCoachResult(null);
    setCoachSuggestions([]);
  }, [resumeId, defaultJobTitle]);

  const runCoach = async () => {
    if (!companyId) return;
    setLoading(true);
    setCoachResult(null);
    setCoachSuggestions([]);
    try {
      const res = await api.post(`/resumes/${resumeId}/coach`, {
        company_id: companyId,
        role_family: roleFamily,
        target_job_title: targetJobTitle || undefined,
      });
      setCoachResult(res.data);
      const coachItems = (res.data.actionable_suggestions || [])
        .filter((s) => s.source === 'coach');
      setCoachSuggestions(coachItems);
      if (onSuggestionsUpdated && res.data.pending_suggestions) {
        onSuggestionsUpdated(res.data.pending_suggestions);
      }
    } catch (err) {
      setCoachResult({ error: err.response?.data?.detail || '简历诊断失败' });
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (suggestion) => {
    if (onApplySuggestion) {
      await onApplySuggestion(suggestion);
      setCoachSuggestions((prev) => prev.filter((item) => item.id !== suggestion.id));
    }
  };

  const handleDismiss = async (suggestion) => {
    if (onDismissSuggestion) {
      await onDismissSuggestion(suggestion);
      setCoachSuggestions((prev) => prev.filter((item) => item.id !== suggestion.id));
    }
  };

  return (
    <Card size="small" title={<><RobotOutlined /> AI 简历诊断</>}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12, fontSize: 13 }}
        message="对照目标公司 JD 与录用画像，生成可采纳的改写对照（含 field_path 精确定位）"
      />
      <Row gutter={8}>
        <Col span={24}>
          <Text type="secondary" style={{ fontSize: 12 }}>目标公司</Text>
          <Select
            showSearch
            placeholder="选择公司"
            style={{ width: '100%', marginTop: 4 }}
            value={companyId}
            onChange={setCompanyId}
            optionFilterProp="label"
            options={companies.map((c) => ({
              value: c.id,
              label: `${c.name} (${c.tier_label || c.tier})`,
            }))}
          />
        </Col>
        <Col span={12} style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>岗位方向</Text>
          <Select
            style={{ width: '100%', marginTop: 4 }}
            value={roleFamily}
            onChange={setRoleFamily}
            options={ROLE_FAMILIES}
          />
        </Col>
        <Col span={12} style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>意向职位</Text>
          <Input
            style={{ marginTop: 4 }}
            placeholder="如 Java 开发"
            value={targetJobTitle}
            onChange={(e) => setTargetJobTitle(e.target.value)}
          />
        </Col>
      </Row>
      <Button
        type="primary"
        icon={<FileSearchOutlined />}
        loading={loading}
        onClick={runCoach}
        disabled={!companyId}
        style={{ marginTop: 12 }}
        block
      >
        开始诊断
      </Button>

      <Spin spinning={loading}>
        {coachResult?.error && (
          <Alert type="error" message={coachResult.error} style={{ marginTop: 12 }} />
        )}
        {coachResult && !coachResult.error && (
          <div style={{ marginTop: 12, maxHeight: 480, overflowY: 'auto' }}>
            <Paragraph style={{ fontSize: 13 }}>{coachResult.coach?.summary}</Paragraph>
            {coachResult.coach?.priority_actions?.length > 0 && (
              <>
                <Title level={5} style={{ fontSize: 14 }}>优先行动</Title>
                <List
                  size="small"
                  dataSource={coachResult.coach.priority_actions}
                  renderItem={(item) => <List.Item style={{ padding: '4px 0' }}>• {item}</List.Item>}
                />
              </>
            )}
            {coachResult.gaps && (
              <Row gutter={8} style={{ marginTop: 8 }}>
                <Col span={12}>
                  <Text type="secondary" style={{ fontSize: 12 }}>缺技能</Text>
                  <div style={{ marginTop: 4 }}>
                    {(coachResult.gaps.skills_missing || []).slice(0, 5).map((s) => (
                      <Tag key={s} color="red" style={{ marginBottom: 4 }}>{s}</Tag>
                    ))}
                  </div>
                </Col>
                <Col span={12}>
                  <Text type="secondary" style={{ fontSize: 12 }}>已匹配</Text>
                  <div style={{ marginTop: 4 }}>
                    {(coachResult.gaps.skills_matched || []).slice(0, 5).map((s) => (
                      <Tag key={s} color="green" style={{ marginBottom: 4 }}>{s}</Tag>
                    ))}
                  </div>
                </Col>
              </Row>
            )}

            {coachSuggestions.length > 0 && (
              <>
                <Divider style={{ margin: '12px 0' }} />
                <Text strong style={{ fontSize: 14 }}>诊断建议 · 对照采纳</Text>
                <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 8 }}>
                  每条建议含 field_path，采纳后精确写回对应字段
                </Text>
                {coachSuggestions.map((item) => (
                  <SuggestionDiffCard
                    key={item.id}
                    suggestion={item}
                    resumeId={resumeId}
                    loading={applyingId === item.id}
                    onAccept={handleAccept}
                    onDismiss={handleDismiss}
                  />
                ))}
              </>
            )}

            {coachSuggestions.length === 0 && (
              <Alert
                style={{ marginTop: 12 }}
                type="warning"
                showIcon
                message="暂无带改写示例的建议"
                description="AI 未返回 example_before/after，可调整意向职位后重试"
              />
            )}
          </div>
        )}
      </Spin>
    </Card>
  );
}

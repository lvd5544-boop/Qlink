import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  List,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  message,
  Divider,
} from 'antd';
import {
  BarChartOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import { createIdempotencyTracker } from '../../utils/idempotency';

const { Title, Text, Paragraph } = Typography;

const TIER_OPTIONS = [
  { value: '', label: '全部公司' },
  { value: 'soe', label: '国有企业' },
  { value: 'foreign', label: '外资企业' },
  { value: 'fortune500', label: '世界 500 强' },
  { value: 'hot', label: '热门民企' },
];

const ROLE_FAMILIES = [
  { value: 'general', label: '综合' },
  { value: 'engineering', label: '技术/研发' },
  { value: 'product', label: '产品' },
  { value: 'data', label: '数据' },
  { value: 'management', label: '管理' },
  { value: 'sales', label: '销售/市场' },
  { value: 'finance', label: '财务/金融' },
];

function FreqBars({ data, color = '#4f46e5' }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (!entries.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
  const max = entries[0][1] || 1;
  return (
    <Space orientation="vertical" style={{ width: '100%' }} size={8}>
      {entries.map(([label, count]) => (
        <div key={label}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <Text>{label}</Text>
            <Text type="secondary">{count}</Text>
          </div>
          <Progress percent={Math.round((count / max) * 100)} showInfo={false} strokeColor={color} size="small" />
        </div>
      ))}
    </Space>
  );
}

export default function Analytics() {
  const [companies, setCompanies] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [tier, setTier] = useState('');
  const [companyId, setCompanyId] = useState(null);
  const [roleFamily, setRoleFamily] = useState('general');
  const [profile, setProfile] = useState(null);
  const [coachResult, setCoachResult] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [loadingCoach, setLoadingCoach] = useState(false);
  const coachIdempotency = useRef(createIdempotencyTracker('analytics-resume-coach'));

  const userId = localStorage.getItem('user_id');

  useEffect(() => {
    const timer = setTimeout(async () => {
      const params = tier ? { tier } : {};
      try {
        const response = await api.get('/analytics/companies', { params });
        setCompanies(response.data);
      } catch {
        message.error('加载公司列表失败');
      }
      if (userId) {
        api.get(`/resumes/${userId}`).then((response) => setResumes(response.data || [])).catch(() => {});
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [tier, userId]);

  const loadProfile = useCallback(async () => {
    if (!companyId) return;
    setLoadingProfile(true);
    try {
      const res = await api.get(`/analytics/companies/${companyId}/profile`, {
        params: { role_family: roleFamily },
      });
      setProfile(res.data);
    } catch {
      message.error('加载公司画像失败');
    } finally {
      setLoadingProfile(false);
    }
  }, [companyId, roleFamily]);

  useEffect(() => {
    if (!companyId) return undefined;
    const timer = setTimeout(loadProfile, 0);
    return () => clearTimeout(timer);
  }, [companyId, loadProfile]);

  const runCoach = async (values) => {
    const cid = companyId || values.company_id;
    if (!cid) {
      message.warning('请先在「市场洞察」或此处选择目标公司');
      return;
    }
    const requestPayload = {
      resume_id: values.resume_id,
      company_id: cid,
      role_family: roleFamily,
      target_job_title: values.target_job_title,
    };
    const idempotencyKey = coachIdempotency.current.keyFor(requestPayload);
    setLoadingCoach(true);
    setCoachResult(null);
    try {
      const res = await api.post(
        '/analytics/resume-coach',
        requestPayload,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      coachIdempotency.current.complete(idempotencyKey);
      setCoachResult(res.data);
      message.success('简历诊断完成');
    } catch (err) {
      message.error(getApiErrorMessage(err, '简历诊断失败'));
    } finally {
      setLoadingCoach(false);
    }
  };

  const jdInsight =
    profile?.jd_insights?.find((i) => i.role_family === roleFamily) || profile?.jd_insights?.[0];
  const roleMarketFallback = profile?.role_market_fallback;
  const effectiveJdInsight = jdInsight?.jd_sample_size ? jdInsight : roleMarketFallback;
  const usingRoleFallback = !jdInsight?.jd_sample_size && Boolean(roleMarketFallback?.jd_sample_size);
  const marketTab = (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Text type="secondary">公司类型</Text>
          <Select
            style={{ width: '100%', marginTop: 8 }}
            options={TIER_OPTIONS}
            value={tier}
            onChange={(v) => {
              setTier(v);
              setCompanyId(null);
              setProfile(null);
            }}
          />
        </Col>
        <Col xs={24} md={10}>
          <Text type="secondary">目标公司</Text>
          <Select
            showSearch
            placeholder="选择 500 强或热门企业"
            style={{ width: '100%', marginTop: 8 }}
            value={companyId}
            onChange={setCompanyId}
            optionFilterProp="label"
            options={companies.map((c) => ({
              value: c.id,
              label: `${c.name} (${c.tier_label || c.tier})`,
            }))}
          />
        </Col>
        <Col xs={24} md={6}>
          <Text type="secondary">岗位方向</Text>
          <Select
            style={{ width: '100%', marginTop: 8 }}
            value={roleFamily}
            onChange={setRoleFamily}
            options={ROLE_FAMILIES}
          />
        </Col>
      </Row>

      <Spin spinning={loadingProfile}>
        {!companyId ? (
          <Alert message="请先选择目标公司，查看公开岗位的常见要求" type="info" showIcon />
        ) : profile ? (
          <Row gutter={[16, 16]}>
            <Col xs={24}>
              <Card className="content-card" title={usingRoleFallback ? '同类岗位通常看重什么' : '这家公司公开岗位通常看重什么'} extra={
                effectiveJdInsight?.jd_sample_size ? (
                  <Tag color={usingRoleFallback ? 'blue' : undefined}>
                    {usingRoleFallback ? '同类岗位参考' : '信息充足'}
                  </Tag>
                ) : (
                  <Tag color="orange">信息较少</Tag>
                )
              }>
                {effectiveJdInsight?.jd_sample_size ? (
                  <>
                    {usingRoleFallback && (
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 12 }}
                        message="这家公司的公开岗位较少，以下展示同类岗位的常见要求。"
                        description="用于帮助你准备方向，不代表这家公司的硬性标准。"
                      />
                    )}
                    <Title level={5}>硬技能</Title>
                    <FreqBars data={effectiveJdInsight.skill_freq} />
                    <Divider />
                    <Title level={5}>软实力</Title>
                    <FreqBars data={effectiveJdInsight.soft_skill_freq} color="#10b981" />
                    <Divider />
                    <Title level={5}>领导力相关</Title>
                    <FreqBars data={effectiveJdInsight.leadership_freq} color="#f59e0b" />
                  </>
                ) : (
                  <Empty description="暂时没有足够信息。可以更换公司或岗位方向。" />
                )}
              </Card>
            </Col>
          </Row>
        ) : null}
      </Spin>
    </Space>
  );

  const coachTab = (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="选择公司和简历后，我们会告诉你优先补强哪些真实经历。"
      />
      <Form layout="vertical" onFinish={runCoach}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item name="resume_id" label="选择简历" rules={[{ required: true }]}>
              <Select
                placeholder="选择要诊断的简历"
                options={resumes.map((r) => ({
                  value: r.id,
                  label: r.parsed?.name ? `${r.parsed.name} 的简历` : `简历 ${r.id.slice(0, 8)}`,
                }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="company_id" label="目标公司" initialValue={companyId}>
              <Select
                showSearch
                placeholder="目标公司"
                value={companyId}
                onChange={setCompanyId}
                options={companies.map((c) => ({ value: c.id, label: c.name }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="target_job_title" label="意向职位">
              <Input placeholder="如：Java 开发工程师" />
            </Form.Item>
          </Col>
        </Row>
        <Button type="primary" htmlType="submit" loading={loadingCoach} icon={<FileSearchOutlined />}>
          开始简历诊断
        </Button>
      </Form>

      {coachResult && (
        <Card className="content-card" title="诊断结果">
          <Paragraph>{coachResult.coach?.summary}</Paragraph>
          {coachResult.coach?.priority_actions?.length > 0 && (
            <>
              <Title level={5}>优先行动</Title>
              <List
                size="small"
                dataSource={coachResult.coach.priority_actions}
                renderItem={(item) => <List.Item>• {item}</List.Item>}
              />
            </>
          )}
          {coachResult.gaps && (
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={8}>
                <Text type="secondary">缺少技能</Text>
                <div style={{ marginTop: 8 }}>
                  {(coachResult.gaps.skills_missing || []).map((s) => (
                    <Tag key={s} color="red" style={{ marginBottom: 4 }}>
                      {s}
                    </Tag>
                  ))}
                </div>
              </Col>
              <Col span={8}>
                <Text type="secondary">软实力差距</Text>
                <div style={{ marginTop: 8 }}>
                  {(coachResult.gaps.soft_skills_missing || []).map((s) => (
                    <Tag key={s} color="orange" style={{ marginBottom: 4 }}>
                      {s}
                    </Tag>
                  ))}
                </div>
              </Col>
              <Col span={8}>
                <Text type="secondary">已匹配技能</Text>
                <div style={{ marginTop: 8 }}>
                  {(coachResult.gaps.skills_matched || []).map((s) => (
                    <Tag key={s} color="green" style={{ marginBottom: 4 }}>
                      {s}
                    </Tag>
                  ))}
                </div>
              </Col>
            </Row>
          )}
          <Divider />
          <Title level={5}>分条建议</Title>
          <List
            dataSource={coachResult.coach?.suggestions || []}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={item.priority === '高' ? 'red' : item.priority === '中' ? 'orange' : 'default'}>
                        {item.priority}
                      </Tag>
                      {item.section}
                    </Space>
                  }
                  description={
                    <div>
                      <Text strong>问题：</Text>
                      {item.issue}
                      <br />
                      <Text strong>建议：</Text>
                      {item.advice}
                      {item.example_after && (
                        <>
                          <br />
                          <Text type="success">示例：{item.example_after}</Text>
                        </>
                      )}
                    </div>
                  }
                />
              </List.Item>
            )}
          />
          {coachResult.coach?.soft_skill_advice && (
            <Alert message={coachResult.coach.soft_skill_advice} type="warning" showIcon style={{ marginTop: 12 }} />
          )}
          {coachResult.coach?.school_advice && (
            <Alert message={coachResult.coach.school_advice} type="info" showIcon style={{ marginTop: 8 }} />
          )}
        </Card>
      )}

      {coachResult?.battle_card && (
        <Card className="content-card" title="投递作战卡" style={{ marginTop: 16 }}>
          <Paragraph>{coachResult.battle_card.positioning}</Paragraph>

          <Title level={5}>简历重点</Title>
          <List
            size="small"
            dataSource={coachResult.battle_card.resume_focus || []}
            renderItem={(item) => <List.Item>• {item}</List.Item>}
          />

          <Divider />
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Title level={5}>已匹配能力</Title>
              <Space wrap>
                {(coachResult.battle_card.matched_signals || []).map((s) => (
                  <Tag key={s} color="green">{s}</Tag>
                ))}
              </Space>
            </Col>
            <Col xs={24} md={12}>
              <Title level={5}>缺失能力</Title>
              <Space wrap>
                {(coachResult.battle_card.missing_signals || []).map((s) => (
                  <Tag key={s} color="orange">{s}</Tag>
                ))}
              </Space>
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8, fontSize: 12 }}
                message="如果没有真实经历，不建议硬写"
              />
            </Col>
          </Row>

          <Divider />
          <Title level={5}>可补强经历</Title>
          <List
            size="small"
            dataSource={coachResult.battle_card.experience_to_strengthen || []}
            renderItem={(item) => <List.Item>• {item}</List.Item>}
          />

          {(coachResult.battle_card.do_not_fake || []).length > 0 && (
            <>
              <Divider />
              <Title level={5}>不建议硬写内容</Title>
              <List
                size="small"
                dataSource={coachResult.battle_card.do_not_fake}
                renderItem={(item) => <List.Item style={{ color: '#64748b' }}>• {item}</List.Item>}
              />
            </>
          )}

          <Divider />
          <Title level={5}>面试高频追问</Title>
          <List
            size="small"
            dataSource={coachResult.battle_card.interview_questions || []}
            renderItem={(item) => <List.Item>• {item}</List.Item>}
          />

          <Divider />
          <Title level={5}>需要准备的证据</Title>
          <List
            size="small"
            dataSource={coachResult.battle_card.evidence_to_prepare || []}
            renderItem={(item) => <List.Item>• {item}</List.Item>}
          />
        </Card>
      )}
    </Space>
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            公司与岗位参考
          </Title>
          <Text type="secondary">
            看公开岗位通常重视什么，并据此优化你的简历。
          </Text>
        </div>
      </div>

      <Tabs
        style={{ marginTop: 20 }}
        items={[
          { key: 'market', label: <span><BarChartOutlined /> 市场洞察</span>, children: marketTab },
          { key: 'coach', label: <span><FileSearchOutlined /> 简历诊断</span>, children: coachTab },
        ]}
      />
    </div>
  );
}

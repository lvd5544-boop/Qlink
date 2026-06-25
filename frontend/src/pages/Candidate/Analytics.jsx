import { useEffect, useState } from 'react';
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
  TeamOutlined,
  FileSearchOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import api from '../../api';

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

const SCHOOL_TIERS = ['985', '211', '双一流', '其他'];

function FreqBars({ data, color = '#4f46e5' }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (!entries.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
  const max = entries[0][1] || 1;
  return (
    <Space direction="vertical" style={{ width: '100%' }} size={8}>
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
  const [submitLoading, setSubmitLoading] = useState(false);
  const [mySubmissions, setMySubmissions] = useState([]);
  const [form] = Form.useForm();
  const [syncing, setSyncing] = useState(false);
  const [syncingForum, setSyncingForum] = useState(false);
  const [dataSources, setDataSources] = useState([]);
  const [methodology, setMethodology] = useState('');

  const userId = localStorage.getItem('user_id');

  const loadCompanies = async (t) => {
    const params = t ? { tier: t } : {};
    const res = await api.get('/analytics/companies', { params });
    setCompanies(res.data);
  };

  const syncJobSources = async () => {
    setSyncing(true);
    try {
      await api.post('/jobs/sync-sources');
      message.success('国企/外企岗位 JD 已同步');
      if (companyId) loadProfile();
      loadCompanies(tier);
    } catch {
      message.error('岗位同步失败，请确认后端与网络正常');
    } finally {
      setSyncing(false);
    }
  };

  const syncForumInsights = async () => {
    setSyncingForum(true);
    try {
      await api.post('/analytics/sync-forum-insights');
      message.success('网络经验帖已抓取并完成统计建模');
      if (companyId) loadProfile();
    } catch {
      message.error('论坛数据同步失败（可能受网络或平台限流影响）');
    } finally {
      setSyncingForum(false);
    }
  };

  useEffect(() => {
    loadCompanies(tier).catch(() => message.error('加载公司列表失败'));
    api.get('/analytics/data-sources').then((r) => {
      setDataSources(r.data?.sources || []);
      setMethodology(r.data?.methodology || '');
    }).catch(() => {});
    if (userId) {
      api.get(`/resumes/${userId}`).then((r) => setResumes(r.data || [])).catch(() => {});
      api.get('/analytics/hired-profiles/mine').then((r) => setMySubmissions(r.data || [])).catch(() => {});
    }
  }, [tier]);

  const loadProfile = async () => {
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
  };

  useEffect(() => {
    if (companyId) loadProfile();
  }, [companyId, roleFamily]);

  const runCoach = async (values) => {
    const cid = companyId || values.company_id;
    if (!cid) {
      message.warning('请先在「市场洞察」或此处选择目标公司');
      return;
    }
    setLoadingCoach(true);
    setCoachResult(null);
    try {
      const res = await api.post('/analytics/resume-coach', {
        resume_id: values.resume_id,
        company_id: cid,
        role_family: roleFamily,
        target_job_title: values.target_job_title,
      });
      setCoachResult(res.data);
      message.success('简历诊断完成');
    } catch (err) {
      message.error(err.response?.data?.detail || '简历诊断失败');
    } finally {
      setLoadingCoach(false);
    }
  };

  const submitHiredProfile = async (values) => {
    setSubmitLoading(true);
    try {
      const res = await api.post('/analytics/hired-profiles', {
        ...values,
        skills: (values.skills || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        soft_skills: (values.soft_skills || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        leadership_examples: (values.leadership_examples || '')
          .split(/[,，]/)
          .map((s) => s.trim())
          .filter(Boolean),
      });
      message.success(res.data?.msg || '录用画像已提交');
      form.resetFields();
      const r = await api.get('/analytics/hired-profiles/mine');
      setMySubmissions(r.data || []);
      if (companyId && res.data?.status === 'approved') loadProfile();
    } catch (err) {
      message.error(err.response?.data?.detail || '提交失败');
    } finally {
      setSubmitLoading(false);
    }
  };

  const jdInsight =
    profile?.jd_insights?.find((i) => i.role_family === roleFamily) || profile?.jd_insights?.[0];
  const hiredBench =
    profile?.hired_benchmarks?.find((b) => b.role_family === roleFamily) ||
    profile?.hired_benchmarks?.[0];

  const marketTab = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
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
          <Alert message="请先选择目标公司，查看公开招聘偏好与录用画像参考" type="info" showIcon />
        ) : profile ? (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Card className="content-card" title="公开招聘偏好（JD 聚合)" extra={
                jdInsight?.jd_sample_size ? (
                  <Tag>{jdInsight.jd_sample_size} 个岗位样本</Tag>
                ) : (
                  <Tag color="orange">样本不足</Tag>
                )
              }>
                {jdInsight?.jd_sample_size ? (
                  <>
                    <Title level={5}>硬技能</Title>
                    <FreqBars data={jdInsight.skill_freq} />
                    <Divider />
                    <Title level={5}>软实力</Title>
                    <FreqBars data={jdInsight.soft_skill_freq} color="#10b981" />
                    <Divider />
                    <Title level={5}>领导力相关</Title>
                    <FreqBars data={jdInsight.leadership_freq} color="#f59e0b" />
                  </>
                ) : (
                  <Empty description="该公司暂无已匹配的 JD 数据，请稍后或触发数据重建" />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card
                className="content-card"
                title={
                  <span>
                    <TeamOutlined /> 录用画像（统计模型）
                  </span>
                }
                extra={
                  hiredBench?.source === 'demo_preview' ? (
                    <Tag color="red">演示语料</Tag>
                  ) : hiredBench?.source === 'insufficient_forum' ? (
                    <Tag color="orange">样本不足</Tag>
                  ) : hiredBench?.sample_tier === 'exploratory' ? (
                    <Tag color="gold">探索性（10+帖）</Tag>
                  ) : hiredBench?.sample_tier === 'credible' ? (
                    <Tag color="purple">较可信（30+帖）</Tag>
                  ) : hiredBench?.sample_tier === 'stable' ? (
                    <Tag color="green">较稳定（100+帖）</Tag>
                  ) : hiredBench?.source === 'statistical_forum' ? (
                    <Tag color="purple">网络经验帖</Tag>
                  ) : (
                    <Tag>统计估计</Tag>
                  )
                }
              >
                {hiredBench ? (
                  <>
                    {hiredBench.methodology && (
                      <Alert type="info" message={hiredBench.methodology} style={{ marginBottom: 12 }} showIcon />
                    )}
                    <Space wrap>
                      <Text type="secondary">
                        网络帖样本：{hiredBench.n_samples}
                        {hiredBench.statistical_summary?.n_samples_live != null && (
                          <>（真实网络 {hiredBench.statistical_summary.n_samples_live}）</>
                        )}
                      </Text>
                      {hiredBench.statistical_summary?.sample_tier_label && (
                        <Text type="secondary">{hiredBench.statistical_summary.sample_tier_label}</Text>
                      )}
                      {hiredBench.confidence_score != null && (
                        <Text type="secondary">
                          模型置信度：{Math.round(hiredBench.confidence_score * 100)}%
                        </Text>
                      )}
                    </Space>
                    {(hiredBench.statistical_summary?.conclusions || []).length > 0 && (
                      <>
                        <Divider />
                        <Title level={5}>统计结论</Title>
                        <List
                          size="small"
                          dataSource={hiredBench.statistical_summary.conclusions}
                          renderItem={(line) => <List.Item style={{ padding: '4px 0' }}>{line}</List.Item>}
                        />
                      </>
                    )}
                    {hiredBench.source === 'insufficient_forum' ? (
                      <Alert
                        type="warning"
                        style={{ marginTop: 12 }}
                        showIcon
                        message={hiredBench.notes || '样本不足，请先同步网络经验数据'}
                      />
                    ) : hiredBench.source === 'demo_preview' ? (
                      <>
                        <Alert
                          type="error"
                          style={{ marginTop: 12 }}
                          showIcon
                          message={hiredBench.notes || '以下为演示语料预览，不能作为真实录用统计'}
                        />
                        <Divider />
                        <Title level={5}>学校层次（演示语料 · 提及频率）</Title>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                          {hiredBench.statistical_summary?.school_tier_disclaimer}
                        </Text>
                        <FreqBars data={hiredBench.school_tier_dist} color="#6366f1" />
                        <Divider />
                        <Title level={5}>技能信号（演示）</Title>
                        <FreqBars data={hiredBench.skill_freq} />
                        <Divider />
                        <Title level={5}>软实力信号（演示）</Title>
                        <FreqBars data={hiredBench.soft_skill_freq} color="#10b981" />
                      </>
                    ) : (
                      <>
                        <Divider />
                        <Title level={5}>学校层次（公开样本提及频率）</Title>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                          {hiredBench.statistical_summary?.school_tier_disclaimer ||
                            '仅反映经验帖提及频率，不代表企业官方筛选标准，不建议作为唯一判断依据。'}
                        </Text>
                        <FreqBars data={hiredBench.school_tier_dist} color="#6366f1" />
                        <Divider />
                        <Title level={5}>技能信号</Title>
                        <FreqBars data={hiredBench.skill_freq} />
                        <Divider />
                        <Title level={5}>软实力信号</Title>
                        <FreqBars data={hiredBench.soft_skill_freq} color="#10b981" />
                        {hiredBench.source_breakdown && Object.keys(hiredBench.source_breakdown).length > 0 && (
                          <>
                            <Divider />
                            <Title level={5}>帖子来源构成</Title>
                            <FreqBars data={hiredBench.source_breakdown} color="#94a3b8" />
                          </>
                        )}
                      </>
                    )}
                  </>
                ) : (
                  <Empty description="暂无录用画像，请先同步网络经验数据" />
                )}
              </Card>
            </Col>
          </Row>
        ) : null}
      </Spin>
    </Space>
  );

  const coachTab = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="简历诊断：对照 JD 偏好与录用画像，指导你在已有经历中补强证据（量化结果、协调范围），而非编造软实力。需配置 LLM API Key。"
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
            renderItem={(item, idx) => (
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
    </Space>
  );

  const submitTab = (
    <Row gutter={[24, 24]}>
      <Col xs={24} lg={14}>
        <Card className="content-card" title="补充参考（自愿、权重≤12%）">
          <Paragraph type="secondary">
            录用画像主结论来自公开网络帖统计（展示≥10 帖，较可信≥30，较稳定≥100）。
            此处提交默认待审核，通过后权重≤12%，不会主导统计结论。
          </Paragraph>
          <Form form={form} layout="vertical" onFinish={submitHiredProfile}>
            <Form.Item name="company_id" label="录用公司" rules={[{ required: true }]}>
              <Select
                showSearch
                options={companies.map((c) => ({ value: c.id, label: c.name }))}
              />
            </Form.Item>
            <Form.Item name="role_title" label="录用职位" rules={[{ required: true }]}>
              <Input placeholder="如：高级后端工程师" />
            </Form.Item>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="school" label="毕业院校">
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="school_tier" label="院校层次">
                  <Select allowClear options={SCHOOL_TIERS.map((s) => ({ value: s, label: s }))} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="degree" label="学历">
              <Input placeholder="本科 / 硕士 / 博士" />
            </Form.Item>
            <Form.Item name="skills" label="核心技能（逗号分隔）">
              <Input placeholder="Java, Spring, MySQL" />
            </Form.Item>
            <Form.Item name="soft_skills" label="软实力（逗号分隔）">
              <Input placeholder="沟通协作, 跨部门协调, 英语" />
            </Form.Item>
            <Form.Item name="leadership_examples" label="领导力体现（逗号分隔）">
              <Input placeholder="带3人团队, 主导项目交付" />
            </Form.Item>
            <Form.Item name="hired_year" label="录用年份">
              <Input type="number" placeholder="2025" />
            </Form.Item>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
              提交后默认待审核，通过后以极低权重纳入统计；每人每天最多 2 条。
            </Text>
            <Button type="primary" htmlType="submit" loading={submitLoading} icon={<PlusOutlined />}>
              提交录用画像
            </Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} lg={10}>
        <Card className="content-card" title="我的贡献记录">
          {mySubmissions.length ? (
            <List
              dataSource={mySubmissions}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={`${item.company_name} · ${item.role_title}`}
                    description={`${item.school_tier || '—'} · ${item.hired_year || '—'} · ${
                      item.status === 'pending'
                        ? '待审核'
                        : item.status === 'approved'
                          ? '已通过'
                          : item.status === 'rejected'
                            ? '已拒绝'
                            : item.status || '—'
                    }`}
                  />
                </List.Item>
              )}
            />
          ) : (
            <Empty description="暂无提交记录" />
          )}
        </Card>
      </Col>
    </Row>
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            数据分析与简历诊断
          </Title>
          <Text type="secondary">
            JD 偏好来自国企/外企招聘源；录用画像来自网络社区经验帖 + 统计模型（Wilson 区间 / 加权频率）。
          </Text>
        </div>
        <Space>
          <Button loading={syncingForum} onClick={syncForumInsights} type="primary">
            同步网络经验数据
          </Button>
          <Button loading={syncing} onClick={syncJobSources}>
            同步岗位 JD
          </Button>
        </Space>
      </div>
      {(methodology || dataSources.length > 0) && (
        <Alert
          style={{ marginTop: 12 }}
          type="info"
          showIcon
          message="方法论与数据来源"
          description={
            <>
              {methodology && <Paragraph style={{ marginBottom: 8 }}>{methodology}</Paragraph>}
              {dataSources.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {dataSources.map((s) => (
                    <li key={s.id}>{s.name}：{s.description}</li>
                  ))}
                </ul>
              )}
            </>
          }
        />
      )}

      <Tabs
        style={{ marginTop: 20 }}
        items={[
          { key: 'market', label: <span><BarChartOutlined /> 市场洞察</span>, children: marketTab },
          { key: 'coach', label: <span><FileSearchOutlined /> 简历诊断</span>, children: coachTab },
          { key: 'submit', label: <span><TeamOutlined /> 补充参考（低权重）</span>, children: submitTab },
        ]}
      />
    </div>
  );
}

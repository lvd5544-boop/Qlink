import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  List,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  AuditOutlined,
  FilterOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';

const { Paragraph, Text, Title } = Typography;

const HARD_STATUS = {
  pass: { color: 'success', label: '通过' },
  fail: { color: 'error', label: '未满足' },
  unknown: { color: 'warning', label: '信息不足' },
};

const RESULT_STATUS = {
  pending_review: { color: 'processing', label: '待人工复核' },
  reviewed: { color: 'success', label: '已复核' },
  clarification_requested: { color: 'warning', label: '已发起澄清' },
};

const HARD_FIELD_CONFIG = {
  experience: { field: 'years_experience', operator: 'gte' },
  education: { field: 'education_level', operator: 'contains' },
  skill: { field: 'required_skill', operator: 'contains' },
  location: { field: 'location', operator: 'contains' },
  certificate: { field: 'certificate', operator: 'contains' },
  task: { field: 'required_skill', operator: 'contains' },
  other: { field: 'required_skill', operator: 'contains' },
};

export default function Screening() {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobId = searchParams.get('job_id') || '';
  const [jobs, setJobs] = useState([]);
  const [profile, setProfile] = useState(null);
  const [run, setRun] = useState(null);
  const [results, setResults] = useState([]);
  const [resultPage, setResultPage] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [selected, setSelected] = useState(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [hardFilter, setHardFilter] = useState('');
  const [reviewFilter, setReviewFilter] = useState('pending_review');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const hardRequirements = useMemo(
    () => (profile?.layers?.target_role?.requirements || []).filter(
      (item) => item.is_hard_constraint && item.employer_confirmed,
    ),
    [profile],
  );

  const focusRequirements = useMemo(
    () => (profile?.layers?.target_role?.requirements || []).filter(
      (item) => item.employer_confirmed
        && !item.is_hard_constraint
        && item.level !== 'context'
        && ['skill', 'task', 'other'].includes(item.type),
    ),
    [profile],
  );

  useEffect(() => {
    let cancelled = false;
    api.get('/jobs/mine').then((res) => {
      if (cancelled) return;
      const rows = Array.isArray(res.data) ? res.data : [];
      setJobs(rows);
      if (!jobId && rows[0]?.id) {
        setSearchParams({ job_id: rows[0].id }, { replace: true });
      }
    }).catch((error) => {
      if (!cancelled) message.error(getApiErrorMessage(error, '加载岗位失败'));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [jobId, setSearchParams]);

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;
    api.get(`/advisor/jobs/${jobId}/profile`)
      .then((res) => {
        if (!cancelled) {
          setProfile(res.data);
        }
      })
      .catch((error) => {
        if (!cancelled) message.error(getApiErrorMessage(error, '加载岗位画像失败'));
      });
    return () => { cancelled = true; };
  }, [jobId]);

  const loadResults = async (
    runId,
    page = 1,
    pageSize = 20,
    filters = { hard: hardFilter, review: reviewFilter },
  ) => {
    const offset = (page - 1) * pageSize;
    const response = await api.get(`/employer/screening-runs/${runId}/results`, {
      params: {
        limit: pageSize,
        offset,
        hard_status: filters.hard || undefined,
        review_status: filters.review || undefined,
      },
    });
    const items = response.data?.items || [];
    setResults(items);
    setResultPage({
      current: page,
      pageSize,
      total: response.data?.total ?? (offset + items.length),
    });
    setSelectedRowKeys([]);
  };

  const startScreening = async () => {
    if (!jobId) return;
    if (profile?.snapshot?.status !== 'employer_confirmed') {
      message.warning('请先确认岗位的筛选重点');
      return;
    }
    const hardRules = hardRequirements
      .map((requirement, index) => {
        const config = HARD_FIELD_CONFIG[requirement.type];
        if (!config) return null;
        return {
          rule_type: 'hard_constraint',
          field: config.field,
          operator: config.operator,
          // The server derives the authoritative value from JobRequirement.
          value: { text: requirement.canonical_label || requirement.text },
          job_requirement_id: requirement.id,
          employer_confirmed: true,
          legal_basis_note: '招聘方在岗位发布时确认的必须满足条件',
          order_no: index,
        };
      })
      .filter(Boolean);
    const assistiveRules = focusRequirements.flatMap((requirement, index) => {
      const text = requirement.canonical_label || requirement.text;
      const baseOrder = hardRules.length + (index * 2);
      const rules = [{
        rule_type: 'keyword',
        field: 'keyword',
        operator: 'contains',
        value: { text },
        order_no: baseOrder,
      }];
      if (requirement.type === 'skill') {
        rules.push({
          rule_type: 'taxonomy',
          field: 'canonical_skill',
          operator: 'contains',
          value: { text },
          order_no: baseOrder + 1,
        });
      }
      return rules;
    });
    if (!hardRules.length && !assistiveRules.length) {
      message.warning('请先为岗位设置至少一项“必须满足”或“重点参考”');
      return;
    }
    setBusy(true);
    try {
      const created = await api.post(
        `/employer/jobs/${jobId}/screening-runs`,
        {},
        { headers: { 'Idempotency-Key': `screen-create-${jobId}-${Date.now()}` } },
      );
      const configured = await api.post(
        `/employer/screening-runs/${created.data.id}/rules`,
        {
          rules: [...hardRules, ...assistiveRules],
        },
        { headers: { 'Idempotency-Key': `screen-rules-${created.data.id}` } },
      );
      const executed = await api.post(
        `/employer/screening-runs/${configured.data.id}/execute`,
        {},
        { headers: { 'Idempotency-Key': `screen-exec-${configured.data.id}` } },
      );
      setRun(executed.data);
      await loadResults(executed.data.id, 1, resultPage.pageSize);
      setSelected(null);
      message.success(`海选完成，${executed.data.candidate_count} 位候选人进入人工复核`);
    } catch (error) {
      message.error(getApiErrorMessage(error, '海选失败'));
    } finally {
      setBusy(false);
    }
  };

  const openResult = async (resultId) => {
    try {
      const res = await api.get(`/employer/screening-results/${resultId}`);
      setSelected(res.data);
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载结果失败'));
    }
  };

  const markReviewed = async () => {
    if (!selected?.id) return;
    setBusy(true);
    try {
      const res = await api.post(
        `/employer/screening-results/${selected.id}/mark-reviewed`,
        {},
        { headers: { 'Idempotency-Key': `screen-review-${selected.id}` } },
      );
      setSelected(res.data);
      setResults((rows) => rows.map((row) => (
        row.id === res.data.id ? { ...row, status: res.data.status } : row
      )));
      message.success('已标记人工复核');
    } catch (error) {
      message.error(getApiErrorMessage(error, '标记复核失败'));
    } finally {
      setBusy(false);
    }
  };

  const bulkMarkReviewed = async () => {
    if (!run?.id || !selectedRowKeys.length) return;
    setBusy(true);
    try {
      await api.post(
        `/employer/screening-runs/${run.id}/results/mark-reviewed`,
        { result_ids: selectedRowKeys },
        {
          headers: {
            'Idempotency-Key': `screen-bulk-review-${run.id}-${selectedRowKeys.slice().sort().join('-')}`,
          },
        },
      );
      message.success(`已完成 ${selectedRowKeys.length} 位候选人的人工复核标记`);
      await loadResults(run.id, resultPage.current, resultPage.pageSize);
    } catch (error) {
      message.error(getApiErrorMessage(error, '批量标记失败'));
    } finally {
      setBusy(false);
    }
  };

  const askClarification = async () => {
    if (!selected?.id) return;
    const claim = selected.claim_refs?.[0];
    const question = selected.suggested_followups?.[0] || '请补充可验证的职责边界与结果口径。';
    setBusy(true);
    try {
      const res = await api.post(
        `/employer/screening-results/${selected.id}/clarification`,
        {
          claim_id: claim?.claim_id || null,
          claim_text: claim?.text_snapshot || '待澄清主张',
          questions: [question],
        },
        { headers: { 'Idempotency-Key': `screen-clarify-${selected.id}` } },
      );
      setSelected(res.data.result);
      setResults((rows) => rows.map((row) => (
        row.id === res.data.result.id
          ? { ...row, status: res.data.result.status }
          : row
      )));
      message.success('已复用澄清服务发起追问（未新建授权）');
    } catch (error) {
      message.error(getApiErrorMessage(error, '发起澄清失败'));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !profile) {
    return <Spin tip="加载批筛…" />;
  }

  return (
    <div className="employer-screening-page">
      <Card bordered={false} className="content-card">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space>
            <AuditOutlined />
            <Title level={3} style={{ margin: 0 }}>批量初筛与人工复核</Title>
          </Space>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            选择岗位后一次完成海选。系统先整理必须条件、相关经历和信息缺口，
            招聘方再集中复核；不使用风险分，最终去留由人工决定。
          </Paragraph>
          <Space wrap>
            <Select
              style={{ minWidth: 280 }}
              placeholder="选择岗位"
              value={jobId || undefined}
              options={jobs.map((job) => ({
                value: job.id,
                label: job.title,
              }))}
              onChange={(value) => {
                setRun(null);
                setResults([]);
                setResultPage({ current: 1, pageSize: 20, total: 0 });
                setSelected(null);
                setSearchParams({ job_id: value });
              }}
            />
            <Link to={jobId ? `/employer/edit-job/${jobId}` : '/employer/my-jobs'}>
              调整筛选重点
            </Link>
          </Space>
        </Space>
      </Card>

      <Card
        title={<Space><SafetyCertificateOutlined />本次海选依据</Space>}
        className="content-card"
        style={{ marginTop: 16 }}
      >
        {profile?.snapshot?.status !== 'employer_confirmed' ? (
          <Alert
            type="warning"
            showIcon
            message="这个岗位还没有确认筛选重点"
            description="请先完成岗位发布或编辑，逐项选择必须满足、重点参考或仅作背景。"
          />
        ) : (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div>
              <Text strong>必须满足</Text>
              <Space wrap style={{ marginLeft: 12 }}>
                {hardRequirements.length
                  ? hardRequirements.map((item) => <Tag color="red" key={item.id}>{item.text}</Tag>)
                  : <Text type="secondary">未设置；不会因缺少某项信息直接判为未满足</Text>}
              </Space>
            </div>
            <div>
              <Text strong>重点参考</Text>
              <Space wrap style={{ marginLeft: 12 }}>
                {focusRequirements.map((item) => <Tag color="blue" key={item.id}>{item.text}</Tag>)}
              </Space>
            </div>
          </Space>
        )}
        <Space direction="vertical" style={{ width: '100%', marginTop: 12 }}>
          <Space>
            <Button
              type="primary"
              icon={<FilterOutlined />}
              loading={busy}
              onClick={startScreening}
            >
              {run?.status === 'completed' ? '海选最新申请' : '开始海选'}
            </Button>
          </Space>
          {run && (
            <Text type="secondary">
              最近一次海选纳入 {run.candidate_count} 位已授权候选人
            </Text>
          )}
        </Space>
      </Card>

      <Card title="筛选结果" className="content-card" style={{ marginTop: 16 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            value={reviewFilter}
            style={{ width: 150 }}
            options={[
              { value: '', label: '全部复核状态' },
              { value: 'pending_review', label: '待人工复核' },
              { value: 'clarification_requested', label: '已发起澄清' },
              { value: 'reviewed', label: '已复核' },
            ]}
            onChange={(value) => {
              setReviewFilter(value);
              if (run?.id) loadResults(run.id, 1, resultPage.pageSize, { hard: hardFilter, review: value });
            }}
          />
          <Select
            value={hardFilter}
            style={{ width: 150 }}
            options={[
              { value: '', label: '全部条件结果' },
              { value: 'pass', label: '满足必须条件' },
              { value: 'unknown', label: '信息待确认' },
              { value: 'fail', label: '存在未满足项' },
            ]}
            onChange={(value) => {
              setHardFilter(value);
              if (run?.id) loadResults(run.id, 1, resultPage.pageSize, { hard: value, review: reviewFilter });
            }}
          />
          <Button
            disabled={!selectedRowKeys.length}
            loading={busy}
            onClick={bulkMarkReviewed}
          >
            批量标记已复核{selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ''}
          </Button>
        </Space>
        <Table
          rowKey="id"
          dataSource={results}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          pagination={{
            ...resultPage,
            hideOnSinglePage: true,
            showSizeChanger: false,
            onChange: (page, pageSize) => loadResults(run.id, page, pageSize),
          }}
          locale={{
            emptyText: (
              <Empty
                description={run?.status === 'completed'
                  ? (run.candidate_count === 0
                    ? '暂无已授权申请，收到新申请后可再次海选'
                    : '当前筛选条件下暂无候选人')
                  : '尚未执行海选'}
              />
            ),
          }}
          columns={[
            {
              title: '候选人',
              dataIndex: 'candidate_name',
              render: (value) => value || '候选人',
            },
            {
              title: '必须条件',
              dataIndex: 'hard_filter_status',
              render: (value) => {
                const cfg = HARD_STATUS[value] || HARD_STATUS.unknown;
                return <Tag color={cfg.color}>{cfg.label}</Tag>;
              },
            },
            {
              title: '相关经历',
              dataIndex: 'keyword_hits',
              render: (hits = []) => {
                const matched = hits.filter((item) => item.matched).length;
                return matched ? <Tag color="blue">命中 {matched} 项</Tag> : <Text type="secondary">待人工查看</Text>;
              },
            },
            {
              title: '复核状态',
              dataIndex: 'status',
              render: (value) => {
                const cfg = RESULT_STATUS[value] || RESULT_STATUS.pending_review;
                return <Tag color={cfg.color}>{cfg.label}</Tag>;
              },
            },
            {
              title: '操作',
              render: (_, row) => (
                <Button type="link" onClick={() => openResult(row.id)}>查看决策路径</Button>
              ),
            },
          ]}
        />
      </Card>

      {selected && (
        <Card
          title="结果详情与决策审计"
          className="content-card"
          style={{ marginTop: 16 }}
          extra={(
            <Space>
              <Button onClick={markReviewed} loading={busy}>标记已复核</Button>
              <Button onClick={askClarification} loading={busy}>发起澄清</Button>
            </Space>
          )}
        >
          <Space wrap>
            <Tag color={(HARD_STATUS[selected.hard_filter_status] || {}).color}>
              硬条件 {(HARD_STATUS[selected.hard_filter_status] || {}).label}
            </Tag>
            <Tag>信息不足不会被判为未满足</Tag>
            <Tag>最终决定由人工完成</Tag>
          </Space>
          <Collapse
            style={{ marginTop: 12 }}
            items={[
              {
                key: 'evidence',
                label: '证据摘要',
                children: (
                  <List
                    size="small"
                    dataSource={selected.evidence_summary || []}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                ),
              },
              {
                key: 'alts',
                label: '合理替代解释',
                children: (
                  <List
                    size="small"
                    dataSource={selected.alternative_explanations || []}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                ),
              },
              {
                key: 'followups',
                label: '建议追问',
                children: (
                  <List
                    size="small"
                    dataSource={selected.suggested_followups || []}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                ),
              },
              {
                key: 'trace',
                label: '结构化决策路径',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Alert
                      type="info"
                      showIcon
                      message="系统只整理依据，最终判断由你完成"
                      description="先核对岗位硬性要求，再查看关键词与同义表达，最后结合证据、信息缺口和合理解释进行人工复核。"
                    />
                    <Text strong>本次使用的规则</Text>
                    <List
                      size="small"
                      locale={{ emptyText: '没有触发规则' }}
                      dataSource={selected.decision_trace?.rules_fired || []}
                      renderItem={(item) => (
                        <List.Item>
                          {item.rule_type === 'hard_constraint' ? '硬性要求' : '辅助关键词'}
                          {' · '}
                          {item.field}
                        </List.Item>
                      )}
                    />
                    <Text strong>仍需人工确认</Text>
                    <List
                      size="small"
                      locale={{ emptyText: '暂无额外不确定项' }}
                      dataSource={selected.decision_trace?.uncertainties || []}
                      renderItem={(item) => (
                        <List.Item>
                          {item?.category === 'provider_failure'
                            ? 'AI 摘要暂不可用，当前结果仅基于规则'
                            : '部分简历信息不足，请结合原始申请材料确认'}
                        </List.Item>
                      )}
                    />
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
}

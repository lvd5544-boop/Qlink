import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, Card, Col, Collapse, Drawer, Empty, Form, Input, List, Modal, Row,
  Select, Space, Statistic, Tag, Timeline, Typography, message,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../../api';
import CareerGraph from '../../components/CareerGraph';
import { getApiErrorMessage } from '../../utils/apiError';
import { createIdempotencyTracker } from '../../utils/idempotency';

const { Title, Paragraph, Text } = Typography;
function experienceDate(item) {
  const start = item?.data?.start_date;
  const end = item?.data?.end_date;
  if (start || end) return `${start || '开始时间未填'} — ${end || '至今'}`;
  return '时间可稍后补充';
}

function mergeMaps(maps) {
  const nodes = new Map();
  const edges = new Map();
  maps.filter(Boolean).forEach((map) => {
    (map.nodes || []).forEach((node) => nodes.set(node.id, node));
    (map.edges || []).forEach((edge) => {
      const key = edge.id || `${edge.source}:${edge.target}:${edge.relationship || ''}`;
      edges.set(key, { ...edge, id: key });
    });
  });
  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    page: { has_more: maps.some((map) => map?.page?.has_more) },
  };
}

export default function CareerPassport() {
  const navigate = useNavigate();
  const experienceIdempotency = useRef(createIdempotencyTracker('career-experience'));
  const claimActionIdempotency = useRef(createIdempotencyTracker('career-claim-action'));
  const chatIdempotency = useRef(createIdempotencyTracker('career-claim-chat'));
  const [overview, setOverview] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [mapData, setMapData] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [claimDetail, setClaimDetail] = useState(null);
  const [chatText, setChatText] = useState('');
  const [chatAiEnabled, setChatAiEnabled] = useState(true);
  const [form] = Form.useForm();
  const autoImported = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const fetchPage = async () => {
        const mapRequests = ['timeline', 'capability', 'evidence'].map(
          (view) => api.get(`/career-passport/map?view=${view}&limit=100`),
        );
        if (selectedJobId) {
          mapRequests.push(api.get(`/career-passport/map?view=job&limit=100&job_id=${selectedJobId}`));
        }
        const [overviewRes, timelineRes, mapResponses] = await Promise.all([
          api.get('/career-passport/overview'),
          api.get('/career-passport/timeline?limit=50'),
          Promise.all(mapRequests),
        ]);
        return {
          overviewRes,
          timelineRes,
          mapData: mergeMaps(mapResponses.map((response) => response.data)),
        };
      };
      let page = await fetchPage();
      const { overviewRes, timelineRes } = page;
      setOverview(overviewRes.data);
      setTimeline(timelineRes.data?.items || []);
      setMapData(page.mapData);
      if (
        !autoImported.current
        && Number(overviewRes.data?.counts?.claims || 0) > 0
        && Number(overviewRes.data?.counts?.experiences || 0) === 0
      ) {
        autoImported.current = true;
        await api.post('/career-passport/import-resumes');
        page = await fetchPage();
        setOverview(page.overviewRes.data);
        setTimeline(page.timelineRes.data?.items || []);
        setMapData(page.mapData);
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '职业档案加载失败'));
    } finally {
      setLoading(false);
    }
  }, [selectedJobId]);

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    api.get('/browse-jobs', { params: { sort_by: 'created_at' } })
      .then((response) => {
        if (!cancelled) setJobs(Array.isArray(response.data) ? response.data : []);
      })
      .catch(() => {
        if (!cancelled) setJobs([]);
      });
    return () => { cancelled = true; };
  }, []);

  const submitExperience = async (values) => {
    const payload = {
      ...values,
      date_precision: values.start_date ? 'day' : 'unknown',
      source_kind: 'manual',
      workflow_state: 'active',
    };
    const idempotencyKey = experienceIdempotency.current.keyFor(payload);
    try {
      await api.post('/career-passport/experiences', payload, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      experienceIdempotency.current.complete(idempotencyKey);
      message.success('职业经历已加入长期档案');
      setOpen(false);
      form.resetFields();
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存失败'));
    }
  };

  const openClaim = async (claimId) => {
    try {
      const response = await api.get(`/career-passport/claims/${claimId}/history`);
      setClaimDetail(response.data?.claim || null);
    } catch (error) {
      message.error(getApiErrorMessage(error, 'Claim 历史加载失败'));
    }
  };

  const updateClaimState = async (action) => {
    const payload = { claim_id: claimDetail.id, action };
    const idempotencyKey = claimActionIdempotency.current.keyFor(payload);
    try {
      await api.post(`/career-passport/claims/${claimDetail.id}/${action}`, {}, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      claimActionIdempotency.current.complete(idempotencyKey);
      message.success(action === 'confirm' ? '内容已确认' : '内容已删除');
      if (action === 'withdraw') setClaimDetail(null);
      else await openClaim(claimDetail.id);
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, '操作失败'));
    }
  };

  const sendChat = async () => {
    if (!chatText.trim()) return;
    const payload = {
      body: chatText.trim(),
      question_goal: 'clarify',
      ai_enabled: chatAiEnabled,
    };
    const idempotencyKey = chatIdempotency.current.keyFor({
      claim_id: claimDetail.id,
      ...payload,
    });
    try {
      const response = await api.post(`/career-passport/claims/${claimDetail.id}/chat/messages`, payload, {
        headers: { 'Idempotency-Key': idempotencyKey },
      });
      chatIdempotency.current.complete(idempotencyKey);
      setChatText('');
      if (response.data?.clarification_connected) {
        message.success('已记录，并生成规则澄清问题');
      } else if (response.data?.ai_connected) {
        message.success('已记录，并生成 AI 澄清问题');
      } else {
        message.success('澄清内容已记录（AI 已关闭）');
      }
      await openClaim(claimDetail.id);
    } catch (error) {
      message.error(getApiErrorMessage(error, '记录失败'));
    }
  };

  const counts = overview?.counts || {};
  const experiences = timeline.filter((item) => item.type === 'experience');
  return (
    <div>
      <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>我的经历与能力</Title>
          <Paragraph type="secondary">
            这里保存你做过的事。选择岗位或优化简历时，系统会自动使用这些真实经历。
          </Paragraph>
        </div>
        <Space>
          <Button type="text" icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>补充一段经历</Button>
        </Space>
      </Space>

      <Alert
        showIcon
        type="success"
        message={`已整理 ${counts.experiences || 0} 段经历，可以直接用于岗位推荐和简历优化`}
        description="不需要上传全部证明材料。只有在某段重要经历需要加强说服力时，再按需补充即可。"
        style={{ marginBottom: 16 }}
      />
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {[
          ['已整理经历', counts.experiences || 0],
          ['可继续补充的细节', counts.claims || 0],
          ['已添加补充材料', counts.artifacts || 0],
        ].map(([label, value]) => (
          <Col xs={24} md={8} key={label}><Card><Statistic title={label} value={value} /></Card></Col>
        ))}
      </Row>

      <Card
        title="你的经历"
        extra={<Button type="link" onClick={() => navigate('/candidate/advisor')}>用这些经历优化简历</Button>}
        loading={loading}
      >
        {experiences.length ? (
          <List
            dataSource={experiences}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={item.data.title || item.data.organization || '未命名经历'}
                  description={(
                    <Space direction="vertical" size={2}>
                      {item.data.organization && item.data.organization !== item.data.title && (
                        <Text>{item.data.organization}</Text>
                      )}
                      <Text type="secondary">{experienceDate(item)}</Text>
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        ) : <Empty description="上传一份简历，或手动补充第一段经历" />}
      </Card>

      <Card
        title="我的成长与能力图"
        style={{ marginTop: 16 }}
        loading={loading}
        extra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            value={selectedJobId || undefined}
            placeholder="按目标岗位高亮（可选）"
            style={{ width: 280 }}
            onChange={(value) => setSelectedJobId(value || '')}
            options={jobs.map((job) => ({ value: job.id, label: job.title || '未命名岗位' }))}
          />
        )}
      >
        <Paragraph type="secondary">
          一张图同时展示经历、能力、关键细节和补充材料。点击可查看的节点可以继续补充内容。
        </Paragraph>
        <CareerGraph value={mapData} view="unified" onSelectClaim={openClaim} />
        {mapData?.page?.has_more && <Text type="secondary">内容较多，图中优先展示与你当前经历最相关的部分。</Text>}
      </Card>

      <Collapse
        style={{ marginTop: 16 }}
        items={[{
          key: 'record',
          label: '查看修改记录（可选）',
          children: (
            <>
              <Paragraph type="secondary">
                “用户已确认”只代表你确认内容正确，不等于第三方事实认证。
              </Paragraph>
              <Timeline items={timeline.slice(0, 10).map((item) => ({
                children: item.type === 'experience'
                  ? `整理经历：${item.data.title || item.data.organization || '未命名经历'}`
                  : `生成简历版本 ${item.data.version_number || ''}`,
              }))} />
            </>
          ),
        }]}
      />

      <Modal title="添加职业经历" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={submitExperience}>
          <Form.Item name="experience_type" label="经历类型" rules={[{ required: true }]}>
            <Select options={[
              ['work', '工作'], ['project', '项目'], ['education', '教育'],
              ['volunteer', '志愿'], ['freelance', '自由职业'], ['award', '奖项'], ['other', '其他'],
            ].map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item name="organization" label="组织/学校"><Input maxLength={255} /></Form.Item>
          <Form.Item name="title" label="职位/项目标题"><Input maxLength={255} /></Form.Item>
          <Form.Item name="start_date" label="开始日期"><Input type="date" /></Form.Item>
          <Form.Item name="end_date" label="结束日期"><Input type="date" /></Form.Item>
          <Form.Item name="description" label="原始描述"><Input.TextArea rows={5} maxLength={20000} showCount /></Form.Item>
          <Button type="primary" htmlType="submit" block>保存到职业档案</Button>
        </Form>
      </Modal>
      <Drawer
        title="经历中的一个细节"
        width={520}
        open={Boolean(claimDetail)}
        onClose={() => setClaimDetail(null)}
      >
        {claimDetail && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Card size="small">
              <Paragraph>{claimDetail.current_text}</Paragraph>
              <Space wrap>
                <Tag>{claimDetail.confirmation_state === 'user_confirmed' ? '内容已确认' : '请确认是否准确'}</Tag>
                <Tag>{claimDetail.default_visibility === 'private' ? '仅自己可见' : '投递时由你决定'}</Tag>
              </Space>
            </Card>
            <Space>
              <Button type="primary" onClick={() => updateClaimState('confirm')}>确认内容准确</Button>
              <Button danger onClick={() => updateClaimState('withdraw')}>删除这条内容</Button>
            </Space>
            <Card size="small" title="补充这个细节">
              <Space style={{ marginBottom: 8 }}>
                <Text type="secondary">让 AI 帮你追问遗漏的信息</Text>
                <Button size="small" type={chatAiEnabled ? 'primary' : 'default'} onClick={() => setChatAiEnabled((value) => !value)}>
                  {chatAiEnabled ? '已开启' : '已关闭'}
                </Button>
              </Space>
              <Input.TextArea value={chatText} onChange={(event) => setChatText(event.target.value)} rows={3} placeholder="例如：我具体做了什么，结果怎样" />
              <Button onClick={sendChat} style={{ marginTop: 8 }}>保存补充</Button>
            </Card>
            <Collapse
              items={[{
                key: 'claim-history',
                label: '查看来源与修改记录（可选）',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Card size="small" title="补充材料">
                      {claimDetail.evidence?.length ? (
                        <List
                          size="small"
                          dataSource={claimDetail.evidence}
                          renderItem={(item) => (
                            <List.Item>
                              {item.summary || item.artifact_id || '已关联一份材料'}
                            </List.Item>
                          )}
                        />
                      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有补充材料也可以正常使用" />}
                    </Card>
                    <Timeline items={(claimDetail.events || []).map((event) => ({
                      children: `${event.event_type} · ${event.created_at || ''}`,
                    }))} />
                  </Space>
                ),
              }]}
            />
          </Space>
        )}
      </Drawer>
    </div>
  );
}

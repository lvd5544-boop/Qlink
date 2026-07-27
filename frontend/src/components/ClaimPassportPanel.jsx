import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, Empty, Input, List, Select, Space, Tag, Typography, message } from 'antd';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';

const { Text, Paragraph } = Typography;

const evidenceLabels = {
  supported_by_user_evidence: ['有用户证据支持', 'green'],
  not_enough_information: ['信息不足', 'orange'],
  conflict_detected: ['存在冲突', 'red'],
};

const workflowLabels = {
  open: ['待补充', 'gold'],
  answered: ['用户已说明', 'blue'],
  reviewed: ['招聘方已复核提问', 'cyan'],
  withdrawn: ['已撤回', 'default'],
};

export default function ClaimPassportPanel({ resumeId }) {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState({});
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [workflowFilter, setWorkflowFilter] = useState('all');

  const load = useCallback(async (sync = false) => {
    if (!resumeId) return;
    setLoading(true);
    try {
      const res = sync
        ? await api.post(`/resumes/${resumeId}/claims/sync`)
        : await api.get(`/resumes/${resumeId}/claims`);
      setClaims(res.data?.claims || []);
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载履历主张失败'));
    } finally {
      setLoading(false);
    }
  }, [resumeId]);

  useEffect(() => {
    const timer = setTimeout(() => { load(true); }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const addEvidence = async (claimId) => {
    const draft = drafts[claimId] || {};
    if (!draft.summary?.trim()) {
      message.warning('请先填写补充说明');
      return;
    }
    try {
      await api.post(`/resumes/${resumeId}/claims/${claimId}/evidence`, {
        evidence_type: draft.evidence_type || 'user_statement',
        summary: draft.summary,
        source: draft.source || null,
      });
      setDrafts((previous) => ({ ...previous, [claimId]: {} }));
      await load(false);
      message.success('补充说明已保存为用户证据，不等同于第三方认证');
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存证据失败'));
    }
  };

  const withdraw = async (evidenceId) => {
    try {
      await api.delete(`/resumes/${resumeId}/claims/evidence/${evidenceId}`);
      await load(false);
      message.success('补充说明已撤回；历史事件仍保留，但内容已脱敏');
    } catch (error) {
      message.error(getApiErrorMessage(error, '撤回失败'));
    }
  };

  const visibleClaims = claims.filter((claim) => (
    (evidenceFilter === 'all' || claim.evidence_state === evidenceFilter)
    && (workflowFilter === 'all' || claim.workflow_state === workflowFilter)
  ));

  return (
    <Card size="small" title="④ 履历主张（Claim Passport）" loading={loading} style={{ marginTop: 12 }}>
      <Alert
        type="info"
        showIcon
        message="记录来源与处理历史，不代表事实已认证"
        description="可补充自己的说明或引用；招聘方只会看到投递时明确授权的快照。"
        style={{ marginBottom: 12 }}
      />
      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          value={evidenceFilter}
          onChange={setEvidenceFilter}
          options={[{ value: 'all', label: '全部证据状态' }, ...Object.entries(evidenceLabels).map(([value, [label]]) => ({ value, label }))]}
        />
        <Select
          value={workflowFilter}
          onChange={setWorkflowFilter}
          options={[{ value: 'all', label: '全部处理状态' }, ...Object.entries(workflowLabels).map(([value, [label]]) => ({ value, label }))]}
        />
      </Space>
      {claims.length === 0 ? (
        <Empty description="暂无主张，点击“同步主张”从当前简历生成" />
      ) : visibleClaims.length === 0 ? (
        <Empty description="没有符合筛选条件的主张" />
      ) : (
        <Collapse
          items={visibleClaims.map((claim) => {
            const evidenceState = evidenceLabels[claim.evidence_state] || ['信息不足', 'default'];
            const workflowState = workflowLabels[claim.workflow_state] || ['待补充', 'default'];
            const draft = drafts[claim.id] || {};
            return {
              key: claim.id,
              label: (
                <Space wrap>
                  <Text ellipsis style={{ maxWidth: 250 }}>{claim.current_text}</Text>
                  <Tag color={evidenceState[1]}>{evidenceState[0]}</Tag>
                  <Tag color={workflowState[1]}>{workflowState[0]}</Tag>
                </Space>
              ),
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <Paragraph style={{ marginBottom: 0 }}><Text type="secondary">原文：</Text>{claim.original_text}</Paragraph>
                  <Text type="secondary">路径：{claim.field_path} · 类型：{claim.claim_type}</Text>
                  <List
                    size="small"
                    dataSource={claim.evidence || []}
                    locale={{ emptyText: '尚无补充证据' }}
                    renderItem={(item) => (
                      <List.Item actions={item.verification_status !== 'withdrawn' ? [<Button key="withdraw" size="small" danger onClick={() => withdraw(item.id)}>撤回</Button>] : []}>
                        <List.Item.Meta
                          title={<Space><Tag>{item.evidence_type}</Tag><Text>{item.verification_status === 'withdrawn' ? '已撤回（内容已脱敏）' : item.summary}</Text></Space>}
                          description={item.source || '用户补充说明'}
                        />
                      </List.Item>
                    )}
                  />
                  <List
                    size="small"
                    header="修改与处理历史"
                    dataSource={[...(claim.revisions || []).map((item) => ({ ...item, kind: 'revision' })), ...(claim.events || []).map((item) => ({ ...item, kind: 'event' }))]}
                    locale={{ emptyText: '暂无修改或处理历史' }}
                    renderItem={(item) => (
                      <List.Item>
                        <Text type="secondary">
                          {item.kind === 'revision'
                            ? `改写：${item.before_text} → ${item.after_text}`
                            : `事件：${item.event_type}`}
                        </Text>
                      </List.Item>
                    )}
                  />
                  <Select
                    size="small"
                    value={draft.evidence_type || 'user_statement'}
                    onChange={(value) => setDrafts((p) => ({ ...p, [claim.id]: { ...p[claim.id], evidence_type: value } }))}
                    options={[
                      { value: 'user_statement', label: '用户说明' },
                      { value: 'metric_context', label: '指标背景' },
                      { value: 'document_reference', label: '文档引用（不上传原件）' },
                    ]}
                  />
                  <Input.TextArea
                    rows={2}
                    placeholder="补充你自己的背景、角色、指标口径或可撤回引用"
                    value={draft.summary || ''}
                    onChange={(e) => setDrafts((p) => ({ ...p, [claim.id]: { ...p[claim.id], summary: e.target.value } }))}
                  />
                  <Input
                    placeholder="可选：文档名称或链接引用；不要上传身份证、工资单等高敏感原件"
                    value={draft.source || ''}
                    onChange={(e) => setDrafts((p) => ({ ...p, [claim.id]: { ...p[claim.id], source: e.target.value } }))}
                  />
                  <Button size="small" type="primary" onClick={() => addEvidence(claim.id)}>保存补充说明</Button>
                </Space>
              ),
            };
          })}
        />
      )}
      <Button style={{ marginTop: 12 }} onClick={() => load(true)}>同步当前简历主张</Button>
    </Card>
  );
}

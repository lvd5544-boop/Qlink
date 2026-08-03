import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, Empty, Input, List, Select, Space, Tag, Typography, message } from 'antd';
import { AimOutlined } from '@ant-design/icons';
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

export default function ClaimPassportPanel({
  resumeId,
  focusRequest = null,
  onResumeEnriched,
}) {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState({});
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [workflowFilter, setWorkflowFilter] = useState('priority');

  const load = useCallback(async (sync = false) => {
    if (!resumeId) return;
    setLoading(true);
    try {
      const res = sync
        ? await api.post(`/resumes/${resumeId}/claims/sync`)
        : await api.get(`/resumes/${resumeId}/claims`);
      setClaims(res.data?.claims || []);
      if (sync && res.data?.parsed) {
        onResumeEnriched?.(res.data.parsed);
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载履历主张失败'));
    } finally {
      setLoading(false);
    }
  }, [resumeId, onResumeEnriched]);

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

  const requestedClaimIds = new Set(focusRequest?.claimIds || []);
  const focusedKeys = claims
    .filter((claim) => requestedClaimIds.has(claim.id))
    .map((claim) => claim.id);
  const defaultFocusedKeys = focusedKeys.length
    ? focusedKeys
    : (focusRequest?.requestId ? claims.slice(0, 3).map((claim) => claim.id) : []);
  const isPriorityClaim = (claim) => (
    claim.evidence_state === 'conflict_detected'
    || (
      claim.hierarchy_level === 'detail'
      && ['work_experience', 'projects'].includes(claim.section)
      && /\d|%|提升|降低|主导|负责|带领|最高|最低|优化|增长|achiev|improv|led|highest|lowest/i.test(claim.current_text)
    )
  );
  const visibleClaims = claims.filter((claim) => (
    requestedClaimIds.has(claim.id)
    || (
      (evidenceFilter === 'all' || claim.evidence_state === evidenceFilter)
      && (
        workflowFilter === 'all'
        || (
          workflowFilter === 'priority'
          && claim.workflow_state !== 'withdrawn'
          && (claim.hierarchy_level === 'entry' || isPriorityClaim(claim))
        )
        || (workflowFilter === 'active' && claim.workflow_state !== 'withdrawn')
        || claim.workflow_state === workflowFilter
      )
    )
  )).sort((a, b) => {
    const groupOrder = String(a.group_key || '').localeCompare(String(b.group_key || ''));
    if (groupOrder) return groupOrder;
    if (a.hierarchy_level === b.hierarchy_level) return 0;
    return a.hierarchy_level === 'entry' ? -1 : 1;
  });
  const visibleGroupKeys = new Set(visibleClaims.map((claim) => claim.group_key));
  const claimGroups = [...visibleGroupKeys].map((groupKey) => {
    const includeWithdrawn = ['all', 'withdrawn'].includes(workflowFilter);
    const rows = claims.filter((claim) => (
      claim.group_key === groupKey
      && (includeWithdrawn || claim.workflow_state !== 'withdrawn')
    ));
    const entry = rows.find((claim) => claim.hierarchy_level === 'entry');
    return {
      key: groupKey,
      entry,
      details: rows.filter((claim) => claim.hierarchy_level !== 'entry'),
    };
  });
  const openGroupKeys = claimGroups
    .filter((group) => (
      group.entry && (
        requestedClaimIds.has(group.entry.id)
        || group.details.some((claim) => requestedClaimIds.has(claim.id))
      )
    ))
    .map((group) => group.key);

  const locateSource = (claim) => {
    const suffix = claim.item_index == null ? '' : `-${claim.item_index}`;
    const target = document.getElementById(`resume-anchor-${claim.section}${suffix}`)
      || document.getElementById(`resume-anchor-${claim.section}`);
    if (!target) {
      message.info(`来源位置：${claim.source_locator || claim.field_path}`);
      return;
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.animate(
      [
        { boxShadow: '0 0 0 0 rgba(91, 70, 246, 0)' },
        { boxShadow: '0 0 0 5px rgba(91, 70, 246, .22)' },
        { boxShadow: '0 0 0 0 rgba(91, 70, 246, 0)' },
      ],
      { duration: 1400 },
    );
  };

  const renderClaimBody = (claim, allowEvidence = true) => {
    const draft = drafts[claim.id] || {};
    return (
      <Space direction="vertical" style={{ width: '100%' }} size="small">
        <Space wrap>
          <Tag color="purple">{claim.source_locator || claim.field_path}</Tag>
          <Button size="small" type="link" icon={<AimOutlined />} onClick={() => locateSource(claim)}>
            在简历中精准定位
          </Button>
        </Space>
        <Paragraph style={{ marginBottom: 0 }}><Text type="secondary">原文：</Text>{claim.original_text}</Paragraph>
        <Text type="secondary">
          {claim.hierarchy_level === 'entry'
            ? '这是完整经历的目录项；具体行为、结果和指标收在下方细节中。'
            : `字段：${claim.field_path} · 类型：${claim.claim_type}`}
        </Text>
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
        {allowEvidence && (
          <>
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
          </>
        )}
      </Space>
    );
  };

  return (
    <Card size="small" title="④ 经历澄清卡" loading={loading} style={{ marginTop: 12 }}>
      <Alert
        type="info"
        showIcon
        message="先看完整经历，再按需澄清关键细节"
        description="日期只是经历的上下文，不再作为独立 Claim。系统默认只展示对结果、角色或指标真正有帮助的重点；可切换查看全部。这里记录的是来源与澄清过程，不代表事实已认证。"
        style={{ marginBottom: 12 }}
      />
      {focusRequest?.requestId && (
        <Alert
          type="warning"
          showIcon
          closable
          message={focusRequest.title || '请在对应主张中补充证据'}
          description={focusRequest.message}
          style={{ marginBottom: 12 }}
        />
      )}
      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          value={evidenceFilter}
          onChange={setEvidenceFilter}
          options={[{ value: 'all', label: '全部证据状态' }, ...Object.entries(evidenceLabels).map(([value, [label]]) => ({ value, label }))]}
        />
        <Select
          value={workflowFilter}
          onChange={setWorkflowFilter}
          options={[
            { value: 'active', label: '当前主张' },
            { value: 'priority', label: '待澄清重点' },
            { value: 'all', label: '全部处理状态' },
            ...Object.entries(workflowLabels).map(([value, [label]]) => ({ value, label })),
          ]}
        />
      </Space>
      {claims.length === 0 ? (
        <Empty description="暂无主张，点击“同步主张”从当前简历生成" />
      ) : visibleClaims.length === 0 ? (
        <Empty description="没有符合筛选条件的主张" />
      ) : (
        <Collapse
          key={focusRequest?.requestId || 'default'}
          defaultActiveKey={openGroupKeys.length ? openGroupKeys : defaultFocusedKeys}
          items={claimGroups.map((group) => {
            const claim = group.entry || group.details[0];
            const evidenceState = evidenceLabels[claim.evidence_state] || ['信息不足', 'default'];
            const workflowState = workflowLabels[claim.workflow_state] || ['待补充', 'default'];
            return {
              key: group.entry ? group.key : claim.id,
              label: (
                <Space wrap>
                  {group.entry ? <Tag color="geekblue">完整经历</Tag> : <Tag>独立信息</Tag>}
                  <Text ellipsis style={{ maxWidth: 250 }}>{claim.current_text}</Text>
                  {group.entry && <Tag>{group.details.length} 条细节</Tag>}
                  <Tag color={evidenceState[1]}>{evidenceState[0]}</Tag>
                  <Tag color={workflowState[1]}>{workflowState[0]}</Tag>
                </Space>
              ),
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  {group.entry && renderClaimBody(group.entry, false)}
                  {group.entry && group.details.length > 0 && (
                    <Collapse
                      size="small"
                      className="claim-detail-directory"
                      defaultActiveKey={group.details.filter((item) => requestedClaimIds.has(item.id)).map((item) => item.id)}
                      items={group.details.map((detail, index) => {
                        const detailEvidence = evidenceLabels[detail.evidence_state] || ['信息不足', 'default'];
                        return {
                          key: detail.id,
                          label: (
                            <Space wrap>
                              <Text strong>细节 {index + 1}</Text>
                              <Text ellipsis style={{ maxWidth: 360 }}>{detail.current_text}</Text>
                              <Tag color={detailEvidence[1]}>{detailEvidence[0]}</Tag>
                            </Space>
                          ),
                          children: renderClaimBody(detail, true),
                        };
                      })}
                    />
                  )}
                  {!group.entry && renderClaimBody(claim, true)}
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

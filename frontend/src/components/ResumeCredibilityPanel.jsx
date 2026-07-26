import { useRef, useState } from 'react';
import {
  Alert, Button, Card, Collapse, Input, List, Modal, Space, Spin, Tag, Typography, message, Tabs,
} from 'antd';
import {
  AuditOutlined, QuestionCircleOutlined, ClockCircleOutlined, WarningOutlined,
  SendOutlined,
} from '@ant-design/icons';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';
import { getStatusConfig } from '../constants/applicationStatus';
import { createIdempotencyTracker } from '../utils/idempotency';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const WORDING_CATEGORIES = new Set(['职责合理性', '表述模糊点', '语义模糊/包装词', '职责边界', '机构包装/同质化', '业绩表述']);

const STATUS_CONFIG = {
  clear: { color: 'success', label: '未发现明显需澄清项' },
  needs_clarification: { color: 'warning', label: '存在需澄清项' },
  manual_review: { color: 'error', label: '建议人工复核' },
};

const RISK_COLOR = { high: 'red', medium: 'orange', low: 'default' };

function isWordingFinding(f) {
  return f.signal_type === 'wording' || WORDING_CATEGORIES.has(f.category);
}

function isWordingClaim(item) {
  return ['role', 'action', 'skill'].includes(item.claim_type) && item.risk_level !== 'high';
}

function defaultQuestions(claimText) {
  return [
    `请补充「${(claimText || '该 claim').slice(0, 40)}」的具体背景、个人贡献边界与可验证证据。`,
    '相关指标/结果的统计口径和周期是什么？',
  ];
}

function resolveQuestionLines(payload) {
  const qs = (payload.questions || []).filter(Boolean);
  if (qs.length) return qs;
  return defaultQuestions(payload.claim_text);
}

/**
 * 招聘方：履历逻辑一致性 & 可信度筛查
 */
export default function ResumeCredibilityPanel({
  applicationId: applicationIdProp,
  jobId,
  resumeId,
  candidateName,
  onClarificationSent,
  compact = false,
}) {
  const [loading, setLoading] = useState(false);
  const [sendingId, setSendingId] = useState(null);
  const [report, setReport] = useState(null);
  const [meta, setMeta] = useState(null);
  const [resolvedApplicationId, setResolvedApplicationId] = useState(applicationIdProp || null);
  const [clarifyModal, setClarifyModal] = useState(null);
  const auditIdempotency = useRef(createIdempotencyTracker('credibility-audit'));

  const applicationId = applicationIdProp || resolvedApplicationId;
  const canSendClarification = Boolean(applicationId || (jobId && resumeId));

  const runAudit = async () => {
    if (!applicationIdProp && !(jobId && resumeId)) return;
    const requestPayload = applicationIdProp
      ? { application_id: applicationIdProp }
      : { job_id: jobId, resume_id: resumeId };
    const idempotencyKey = auditIdempotency.current.keyFor(requestPayload);
    const requestConfig = { headers: { 'Idempotency-Key': idempotencyKey } };
    setLoading(true);
    try {
      let res;
      if (applicationIdProp) {
        res = await api.get(
          `/applications/${applicationIdProp}/credibility-audit`,
          requestConfig,
        );
      } else {
        res = await api.get(
          `/applications/job/${jobId}/resume/${resumeId}/credibility-audit`,
          requestConfig,
        );
      }
      auditIdempotency.current.complete(idempotencyKey);
      setReport(res.data.report);
      setMeta({
        jobTitle: res.data.job_title,
        candidateName: res.data.candidate_name || candidateName,
        hasApplication: res.data.has_application ?? Boolean(applicationIdProp),
        applicationStatus: res.data.application_status,
        auditRecordId: res.data.audit_record_id,
      });
      if (res.data.application_id) {
        setResolvedApplicationId(res.data.application_id);
      }
      message.success('筛查完成');
    } catch (err) {
      message.error(getApiErrorMessage(err, '筛查失败'));
    } finally {
      setLoading(false);
    }
  };

  const sendFindingFeedback = async (finding, label) => {
    try {
      await api.post('/applications/feedback/audit-finding', {
        label,
        claim_id: finding.claim_id || finding.id,
        finding_id: finding.id,
        finding_snapshot: {
          id: finding.id,
          claim_id: finding.claim_id,
          severity: finding.severity,
          signal_type: finding.signal_type,
          title: finding.title,
          category: finding.category,
        },
        audit_record_id: meta?.auditRecordId,
        application_id: applicationId,
      });
      message.success(label === 'false_positive' ? '已标记为误报' : '感谢反馈');
    } catch (err) {
      message.error(getApiErrorMessage(err, '反馈失败'));
    }
  };

  const openClarifyModal = (payload, itemKey) => {
    if (!canSendClarification) {
      message.warning('缺少申请或岗位/简历信息，无法发起澄清');
      return;
    }
    setClarifyModal({
      itemKey,
      payload,
      questionsText: resolveQuestionLines(payload).join('\n'),
    });
  };

  const submitClarification = async () => {
    if (!clarifyModal) return;
    const questions = clarifyModal.questionsText
      .split('\n')
      .map((q) => q.trim())
      .filter(Boolean);
    if (!questions.length) {
      message.warning('请至少填写一个需澄清的问题');
      return;
    }

    const { payload, itemKey } = clarifyModal;
    setSendingId(itemKey);
    try {
      const body = {
        claim_id: payload.claim_id,
        claim_text: payload.claim_text,
        questions,
        evidence_suggestions: payload.evidence_suggestions || [],
      };
      let res;
      if (applicationId) {
        res = await api.post(`/applications/${applicationId}/clarification-requests`, body);
      } else {
        res = await api.post(
          `/applications/job/${jobId}/resume/${resumeId}/clarification-requests`,
          body,
        );
      }
      if (res.data.application_id) {
        setResolvedApplicationId(res.data.application_id);
      }
      if (res.data.application?.status) {
        setMeta((prev) => ({ ...prev, applicationStatus: res.data.application.status, hasApplication: true }));
      }
      message.success(
        res.data.application_id && !applicationIdProp
          ? '澄清请求已发送，已自动创建申请记录，可在申请记录中查看对话'
          : '澄清请求已发送，申请状态已更新为待澄清',
      );
      setClarifyModal(null);
      onClarificationSent?.(res.data);
    } catch (err) {
      message.error(getApiErrorMessage(err, '发送澄清请求失败'));
    } finally {
      setSendingId(null);
    }
  };

  const statusCfg = report ? STATUS_CONFIG[report.overall_status] || STATUS_CONFIG.needs_clarification : null;

  const renderClarifyButton = (payload, itemKey) => (
    <Button
      type="link"
      size="small"
      icon={<SendOutlined />}
      loading={sendingId === itemKey}
      disabled={!canSendClarification || !report}
      onClick={() => openClarifyModal(payload, itemKey)}
      style={{ padding: 0, marginTop: 4 }}
    >
      发起澄清
    </Button>
  );

  const renderFindingCard = (f, i, keyPrefix = 'finding') => (
    <div
      key={`${keyPrefix}_${i}`}
      style={{
        marginTop: 8, padding: 10, borderRadius: 8,
        border: '1px solid #e2e8f0', background: '#fafafa',
      }}
    >
      <Space wrap style={{ marginBottom: 4 }}>
        <Tag color={RISK_COLOR[f.severity] || 'default'}>{f.severity}</Tag>
        <Text strong style={{ fontSize: 12 }}>{f.category}</Text>
        {f.signal_type === 'wording' && <Tag color="gold">表述问题</Tag>}
      </Space>
      <Paragraph style={{ margin: '4px 0', fontSize: 12 }}>
        <Text type="secondary">声称：</Text>{f.claim}
      </Paragraph>
      <Paragraph style={{ margin: '4px 0', fontSize: 12 }}>{f.issue}</Paragraph>
      {f.possible_explanations?.length > 0 && (
        <div style={{ marginTop: 4, fontSize: 11, color: '#64748b' }}>
          <Text type="secondary">也可能是因为：</Text>
          {f.possible_explanations.map((e, ei) => (
            <div key={ei}>• {e}</div>
          ))}
        </div>
      )}
      {f.mitigated_by_clarification && (
        <Tag color="blue" style={{ marginTop: 4, fontSize: 11 }}>候选人已补充说明</Tag>
      )}
      {renderClarifyButton({
        claim_id: `${keyPrefix}_${i}`,
        claim_text: f.claim,
        questions: f.clarification_questions,
        evidence_suggestions: [],
      }, `${keyPrefix}_${i}`)}
      <Space size={4} style={{ marginTop: 6 }}>
        <Button size="small" type="link" onClick={() => sendFindingFeedback(f, 'useful')}>有用</Button>
        <Button size="small" type="link" onClick={() => sendFindingFeedback(f, 'false_positive')}>误报</Button>
      </Space>
    </div>
  );

  const renderClaimCard = (item, i) => (
    <div
      key={item.claim_id || i}
      style={{
        marginTop: 8, padding: 10, borderRadius: 8,
        border: '1px solid #e2e8f0', background: '#fff',
      }}
    >
      <Space wrap style={{ marginBottom: 4 }}>
        <Tag color={RISK_COLOR[item.risk_level] || 'default'}>{item.risk_level}</Tag>
        <Tag>{item.claim_type}</Tag>
      </Space>
      <Paragraph style={{ margin: '4px 0', fontSize: 12 }}>
        <Text type="secondary">原始 claim：</Text>{item.claim_text}
      </Paragraph>
      {item.reasoning_chain?.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>推理链：</Text>
          {item.reasoning_chain.map((r, ri) => (
            <div key={ri} style={{ fontSize: 11 }}>• {r}</div>
          ))}
        </div>
      )}
      {renderClarifyButton({
        claim_id: item.claim_id,
        claim_text: item.claim_text,
        questions: item.verification_questions,
        evidence_suggestions: item.evidence_suggestions,
      }, item.claim_id || `claim_${i}`)}
    </div>
  );

  const wordingFindings = (report?.findings || []).filter(isWordingFinding);
  const consistencyFindings = (report?.findings || []).filter((f) => !isWordingFinding(f));
  const wordingClaims = (report?.claim_reasoning?.claim_items || []).filter(isWordingClaim);
  const consistencyClaims = (report?.claim_reasoning?.claim_items || []).filter((item) => !isWordingClaim(item));
  const auditTabItems = [
    {
      key: 'wording',
      label: `表述问题 (${wordingFindings.length + wordingClaims.length})`,
      children: (
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            多为写法或角色边界不清，建议追问澄清，勿直接判定不实
          </Text>
          {wordingFindings.map((f, i) => renderFindingCard(f, i, 'wording_f'))}
          {wordingClaims.map((item, i) => renderClaimCard(item, i))}
          {wordingFindings.length + wordingClaims.length === 0 && (
            <Alert type="success" showIcon style={{ marginTop: 8 }} message="未发现明显表述问题" />
          )}
        </div>
      ),
    },
    {
      key: 'consistency',
      label: `事实一致性 (${consistencyFindings.length + consistencyClaims.length})`,
      children: (
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            时间线、职级、指标口径等硬逻辑冲突，建议优先核实
          </Text>
          {consistencyFindings.map((f, i) => renderFindingCard(f, i, 'consistency_f'))}
          {consistencyClaims.map((item, i) => renderClaimCard(item, i))}
          {consistencyFindings.length + consistencyClaims.length === 0 && (
            <Alert type="success" showIcon style={{ marginTop: 8 }} message="未发现明显事实冲突" />
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card
        size="small"
        title={<><AuditOutlined /> 履历一致性审计</>}
        style={{ marginTop: compact ? 0 : 12 }}
        extra={(
          <Button
            type="primary"
            size="small"
            loading={loading}
            onClick={runAudit}
            disabled={!applicationIdProp && !(jobId && resumeId)}
          >
            运行筛查
          </Button>
        )}
      >
        {!applicationId && jobId && resumeId && !meta?.hasApplication && report && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12, fontSize: 12 }}
            message="匹配候选人"
            description="候选人尚未主动申请。发起澄清时将自动创建申请记录，并通知候选人补充说明。"
          />
        )}

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12, fontSize: 12 }}
          message="履历可信度推理"
          description="检测时间线自洽性、角色边界、指标口径与职责合理性。输出「需澄清 / 建议复核 / 证据不足」，不判定造假。"
        />

        <Spin spinning={loading}>
          {!report && !loading && (
            <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
              点击「运行筛查」，生成一致性报告与建议复核项。
            </Paragraph>
          )}

          {report && statusCfg && (
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              {meta && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {meta.candidateName} · {meta.jobTitle || '岗位未指定'}
                  {meta.applicationStatus && (
                    <> · 申请状态：{getStatusConfig(meta.applicationStatus).text}</>
                  )}
                </Text>
              )}
              <Space wrap>
                <Tag color={statusCfg.color}>{statusCfg.label}</Tag>
                <Tag>风险指数 {report.risk_score}/100</Tag>
                <Tag icon={<ClockCircleOutlined />}>估工龄 {report.work_years_estimate} 年</Tag>
              </Space>

              {report.homogeneity_signals && (
                <Alert
                  type={report.homogeneity_signals.template_phrase_count >= 3 ? 'warning' : 'info'}
                  showIcon
                  style={{ fontSize: 12 }}
                  message="同质化/机构包装信号"
                  description={(
                    <>
                      模板句式 {report.homogeneity_signals.template_phrase_count} 处 ·
                      包装词 {report.homogeneity_signals.packaging_word_count} 处。
                      {report.homogeneity_signals.note}
                    </>
                  )}
                />
              )}

              {report.timeline?.length > 0 && (
                <Collapse
                  size="small"
                  items={[{
                    key: 'timeline',
                    label: `统一时间线（${report.timeline.length} 项）`,
                    children: (
                      <List
                        size="small"
                        dataSource={report.timeline}
                        renderItem={(e) => (
                          <List.Item style={{ padding: '4px 0', fontSize: 12 }}>
                            <Tag>{e.type === 'work' ? '工作' : e.type === 'education' ? '教育' : '项目'}</Tag>
                            {e.start} — {e.end} · {e.label}
                          </List.Item>
                        )}
                      />
                    ),
                  }]}
                />
              )}

              {(report.findings?.length > 0 || report.claim_reasoning?.claim_items?.length > 0) ? (
                <div>
                  <Text strong style={{ fontSize: 13 }}>
                    <WarningOutlined /> 发现项（{report.findings?.length || 0} + Claim {report.claim_reasoning?.flagged_claims || 0}）
                  </Text>
                  <Tabs size="small" style={{ marginTop: 8 }} items={auditTabItems} />
                </div>
              ) : (
                <Alert type="success" showIcon message="规则引擎未发现明显冲突" />
              )}

              {report.clarification_questions?.length > 0 && (
                <div>
                  <Text strong style={{ fontSize: 13 }}>
                    <QuestionCircleOutlined /> 建议复核问题
                  </Text>
                  <List
                    size="small"
                    style={{ marginTop: 6 }}
                    dataSource={report.clarification_questions}
                    renderItem={(q) => <List.Item style={{ padding: '4px 0', fontSize: 12 }}>• {q}</List.Item>}
                  />
                </div>
              )}

              <Paragraph type="secondary" style={{ fontSize: 11, marginBottom: 0 }}>
                {report.disclaimer}
              </Paragraph>
            </Space>
          )}
        </Spin>
      </Card>

      <Modal
        title="发起澄清请求"
        open={!!clarifyModal}
        onCancel={() => setClarifyModal(null)}
        onOk={submitClarification}
        okText="发送澄清"
        confirmLoading={!!sendingId}
        destroyOnClose
      >
        {clarifyModal && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <div>
              <Text type="secondary">关于 claim：</Text>
              <Paragraph style={{ margin: '4px 0 0' }}>{clarifyModal.payload.claim_text}</Paragraph>
            </div>
            <div>
              <Text type="secondary">请补充说明（每行一个问题，可编辑）：</Text>
              <TextArea
                rows={5}
                value={clarifyModal.questionsText}
                onChange={(e) => setClarifyModal((prev) => (
                  prev ? { ...prev, questionsText: e.target.value } : prev
                ))}
                style={{ marginTop: 8 }}
              />
            </div>
            <Alert
              type="info"
              showIcon
              message="发送后将自动通知候选人，申请状态变为「待澄清」"
            />
          </Space>
        )}
      </Modal>
    </>
  );
}

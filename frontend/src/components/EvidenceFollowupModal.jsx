import { useEffect, useRef, useState } from 'react';
import {
  Modal, Form, Input, Button, Space, Typography, Alert, Spin, Steps, message, Tag, List, Segmented,
} from 'antd';
import { QuestionCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';
import { createIdempotencyTracker } from '../utils/idempotency';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const INTENT_COLOR = {
  factual: 'green',
  negative: 'default',
  vague: 'orange',
  packaging: 'gold',
  empty: 'default',
};

/**
 * AI 语义忠实扩写：回答追问 → 语义确认 → 预览 claim ledger → 采纳
 */
export default function EvidenceFollowupModal({
  open,
  onClose,
  resumeId,
  entryType,
  entryIndex,
  onRegenerated,
}) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [context, setContext] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const regenerateIdempotency = useRef(createIdempotencyTracker('evidence-regenerate'));
  const [step, setStep] = useState(0);
  const [analysis, setAnalysis] = useState(null);
  const [result, setResult] = useState(null);
  const [rewriteMode, setRewriteMode] = useState('standard');
  const [claimFollowupAnswers, setClaimFollowupAnswers] = useState([]);
  const [clarificationAnswers, setClarificationAnswers] = useState([]);

  useEffect(() => {
    if (!open || !resumeId || entryType == null || entryIndex == null) return undefined;

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setStep(0);
      setResult(null);
      setAnalysis(null);
      setAnswers({});
      setClaimFollowupAnswers([]);
      setClarificationAnswers([]);
      try {
        const res = await api.post(`/resumes/${resumeId}/evidence-followup/questions`, {
          entry_type: entryType,
          index: entryIndex,
        });
        if (cancelled) return;
        setContext(res.data.context);
        setQuestions(res.data.questions || []);
        setClaimFollowupAnswers(res.data.claim_followup_answers || []);
        setClarificationAnswers(res.data.clarification_answers || []);
      } catch (err) {
        if (!cancelled) {
          message.error(getApiErrorMessage(err, '加载追问失败'));
          onClose?.();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [open, resumeId, entryType, entryIndex, onClose]);

  const buildAnswerPayload = () => questions.map((q) => ({
    id: q.id,
    question: q.question,
    answer: (answers[q.id] || '').trim(),
  })).filter((a) => a.answer);

  const fillFromRecord = (record, sourceLabel) => {
    if (!questions.length) {
      message.warning('暂无可用追问项');
      return;
    }
    const qSnippet = (record.question || record.claim_text || '').slice(0, 10);
    const targetQ = questions.find((q) => qSnippet && q.question.includes(qSnippet))
      || questions.find((q) => !((answers[q.id] || '').trim()))
      || questions[0];
    const existing = (answers[targetQ.id] || '').trim();
    setAnswers((prev) => ({
      ...prev,
      [targetQ.id]: existing ? `${existing}；${record.answer}` : record.answer,
    }));
    message.success(`已填入${sourceLabel || ''}回答，请确认后进入下一步`);
  };

  const fillFromInterview = (record) => fillFromRecord(record, 'AI 面试官');
  const fillFromClarification = (record) => fillFromRecord(record, '招聘方澄清');

  const handleAnalyze = async () => {
    const payload = buildAnswerPayload();
    if (payload.length === 0) {
      message.warning('请至少回答一个问题');
      return;
    }
    setAnalyzing(true);
    try {
      const res = await api.post(`/resumes/${resumeId}/evidence-followup/analyze`, {
        entry_type: entryType,
        index: entryIndex,
        answers: payload,
      });
      setAnalysis(res.data.analysis);
      setStep(1);
    } catch (err) {
      message.error(getApiErrorMessage(err, '语义分析失败'));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerate = async () => {
    const payload = buildAnswerPayload();
    const requestPayload = {
      entry_type: entryType,
      index: entryIndex,
      answers: payload,
      rewrite_mode: rewriteMode,
      style_template: 'evidence_forward',
    };
    const idempotencyKey = regenerateIdempotency.current.keyFor(requestPayload);
    setSubmitting(true);
    try {
      const res = await api.post(
        `/resumes/${resumeId}/evidence-followup/regenerate`,
        requestPayload,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      regenerateIdempotency.current.complete(idempotencyKey);
      setResult(res.data);
      setStep(2);
    } catch (err) {
      message.error(getApiErrorMessage(err, '生成失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleApply = () => {
    if (!result) return;
    onRegenerated?.({
      example_before: result.example_before,
      example_after: result.example_after,
      field_path: result.field_path,
      patch: result.patch,
      fidelity_proof: result.fidelity_proof,
      fidelity_result: result.fidelity_result,
      evidence_references: result.evidence_references,
      suggested_text: result.example_after,
      original_text: result.example_before,
    });
    onClose?.();
  };

  return (
    <Modal
      title={<><QuestionCircleOutlined /> AI 语义忠实扩写</>}
      open={open}
      onCancel={onClose}
      width={620}
      footer={null}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16, fontSize: 13 }}
        message="证据优先·招聘方易读"
        description="默认使用“动作 + 任务 + 方法/范围 + 已证实结果”句式。三档模式仅改变表达强度，均不会编造未提及的事实；采纳前会展示语义理解与来源追溯。"
      />

      {step === 1 && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
            改写模式
          </Text>
          <Segmented
            value={rewriteMode}
            onChange={setRewriteMode}
            options={[
              { label: '保守', value: 'conservative', title: '低风险，仅整理事实' },
              { label: '标准', value: 'standard', title: '推荐，职业化表达' },
              { label: '进取', value: 'assertive', title: '更强强调影响力，需要更多证据支撑' },
            ]}
            block
          />
        </div>
      )}

      <Steps
        size="small"
        current={step}
        style={{ marginBottom: 16 }}
        items={[
          { title: '回答追问' },
          { title: '语义确认' },
          { title: '预览采纳' },
        ]}
      />

      <Spin spinning={loading}>
        {step === 0 && context && (
          <>
            <Paragraph type="secondary" style={{ fontSize: 13 }}>
              <Text strong>{context.name}</Text>
              {context.role ? ` · ${context.role}` : ''}
            </Paragraph>
            {context.example_before && context.example_before !== '（暂无描述）' && (
              <div style={{
                padding: '8px 12px', background: '#fef2f2', borderRadius: 8,
                marginBottom: 12, fontSize: 13,
              }}
              >
                原文：{context.example_before}
              </div>
            )}

            {clarificationAnswers.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 8 }}
                  message="招聘方澄清信息"
                  description="以下为招聘方发起的澄清请求中您已回复的内容，可一键填入对应追问框，仍需您确认后才进入忠实改写。"
                />
                <List
                  size="small"
                  dataSource={clarificationAnswers}
                  renderItem={(record) => (
                    <List.Item
                      style={{ padding: '8px 0', alignItems: 'flex-start' }}
                      actions={[
                        <Button
                          key="fill"
                          type="link"
                          size="small"
                          onClick={() => fillFromClarification(record)}
                        >
                          一键填入
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={(
                          <Space wrap size={4}>
                            <Text style={{ fontSize: 12 }}>{record.claim_text || record.job_title || '招聘方澄清'}</Text>
                            {record.match_type === 'recent_candidate' && (
                              <Tag color="default">候选</Tag>
                            )}
                          </Space>
                        )}
                        description={(
                          <Paragraph style={{ fontSize: 12, margin: '4px 0 0' }} type="secondary">
                            {record.answer}
                          </Paragraph>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </div>
            )}

            {claimFollowupAnswers.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 8 }}
                  message="AI 面试官已补充的信息"
                  description="以下为简历追问模式中您已回答的内容，可一键填入对应追问框，仍需您确认后才进入忠实改写。"
                />
                <List
                  size="small"
                  dataSource={claimFollowupAnswers}
                  renderItem={(record) => (
                    <List.Item
                      style={{ padding: '8px 0', alignItems: 'flex-start' }}
                      actions={[
                        <Button
                          key="fill"
                          type="link"
                          size="small"
                          onClick={() => fillFromInterview(record)}
                        >
                          一键填入
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={(
                          <Space wrap size={4}>
                            <Text style={{ fontSize: 12 }}>{record.claim_text || record.question}</Text>
                            {record.match_type === 'recent_candidate' && (
                              <Tag color="default">候选</Tag>
                            )}
                          </Space>
                        )}
                        description={(
                          <Paragraph style={{ fontSize: 12, margin: '4px 0 0' }} type="secondary">
                            {record.answer}
                          </Paragraph>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </div>
            )}

            <Form layout="vertical">
              {questions.map((q) => (
                <Form.Item
                  key={q.id}
                  label={q.question}
                  extra={q.hint ? <Text type="secondary" style={{ fontSize: 12 }}>{q.hint}</Text> : null}
                >
                  <TextArea
                    rows={2}
                    value={answers[q.id] || ''}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                    placeholder="请输入真实数据（写「没有」表示无相关成果，系统不会编造）"
                  />
                </Form.Item>
              ))}
            </Form>

            <Space style={{ marginTop: 8 }}>
              <Button onClick={onClose}>取消</Button>
              <Button type="primary" loading={analyzing} onClick={handleAnalyze}>
                下一步：语义确认
              </Button>
            </Space>
          </>
        )}

        {step === 1 && analysis && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={analysis.interpretation_summary}
            />

            <Text strong style={{ fontSize: 13 }}>系统理解</Text>
            <Paragraph style={{ fontSize: 13, marginTop: 4 }}>
              表层含义：{analysis.surface_meaning}
            </Paragraph>
            {analysis.possible_meanings?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>可能的真实含义（供您确认）：</Text>
                <List
                  size="small"
                  dataSource={analysis.possible_meanings}
                  renderItem={(item) => <List.Item style={{ padding: '2px 0' }}>• {item}</List.Item>}
                />
              </div>
            )}

            {analysis.answer_analysis?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>各回答意图识别：</Text>
                <Space wrap style={{ marginTop: 6 }}>
                  {analysis.answer_analysis.map((a, i) => (
                    <Tag key={i} color={INTENT_COLOR[a.intent] || 'default'}>
                      {a.intent === 'negative' ? '无数据' : a.intent}
                      {a.answer ? `：${a.answer.slice(0, 12)}${a.answer.length > 12 ? '…' : ''}` : ''}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}

            {analysis.needs_clarification?.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="建议补充后再生成"
                description={analysis.needs_clarification.join('；')}
              />
            )}

            {analysis.template_phrases_in_original?.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="原文含常见模板句式"
                description={`检测到：${analysis.template_phrases_in_original.join('、')}。建议用具体事实替换。`}
              />
            )}

            <Space>
              <Button onClick={() => setStep(0)}>返回修改</Button>
              <Button
                type="primary"
                loading={submitting}
                onClick={handleGenerate}
                disabled={!analysis.ready_to_compose}
              >
                确认并生成
              </Button>
            </Space>
          </>
        )}

        {step === 2 && result && (
          <>
            {result.fidelity_note && (
              <Alert type="success" showIcon icon={<SafetyCertificateOutlined />} style={{ marginBottom: 12 }} message={result.fidelity_note} />
            )}

            <Space wrap style={{ marginBottom: 12 }}>
              <Tag>当前模式：{result.rewrite_mode_label || '标准版'}</Tag>
              <Tag color="blue">写作风格：{result.style_label || '证据优先·招聘方易读'}</Tag>
              {result.mode_risk_level && (
                <Tag color={result.mode_risk_level === 'high' ? 'red' : result.mode_risk_level === 'medium' ? 'orange' : 'green'}>
                  风险等级：{result.mode_risk_level}
                </Tag>
              )}
            </Space>

            {result.mode_warnings?.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="模式提示"
                description={result.mode_warnings.join('；')}
              />
            )}

            <Text type="secondary" style={{ fontSize: 12 }}>整合后描述</Text>
            <div style={{
              padding: '12px', background: '#ecfdf5', border: '1px solid #a7f3d0',
              borderRadius: 8, marginTop: 8, marginBottom: 12, fontSize: 14, lineHeight: 1.7,
            }}
            >
              {result.example_after}
            </div>

            {result.claim_ledger?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ fontSize: 13 }}>来源追溯（Claim Ledger）</Text>
                {result.claim_ledger.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      marginTop: 6, padding: '6px 10px', borderRadius: 6,
                      background: item.verifiable ? '#f8fafc' : '#fef2f2',
                      fontSize: 12,
                    }}
                  >
                    <Tag color={item.source === 'original' ? 'blue' : item.source === 'user_answer' ? 'green' : 'red'}>
                      {item.label}
                    </Tag>
                    {item.text}
                  </div>
                ))}
              </div>
            )}

            {!result.has_quantification && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="仍缺少量化数字"
                description="您未提供具体指标，系统未自动编造。可返回补充数字。"
              />
            )}

            <Space>
              <Button onClick={() => setStep(0)}>返回修改</Button>
              <Button type="primary" onClick={handleApply}>采纳到简历</Button>
            </Space>
          </>
        )}
      </Spin>
    </Modal>
  );
}

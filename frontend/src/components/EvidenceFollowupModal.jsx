import { useEffect, useState } from 'react';
import {
  Modal, Form, Input, Button, Space, Typography, Alert, Spin, Steps, message,
} from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import api from '../api';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * AI 证据追问弹窗：缺量化时展示 2~3 问，回答后生成带数字的 example_after。
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
  const [context, setContext] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!open || !resumeId || entryType == null || entryIndex == null) return undefined;

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setStep(0);
      setResult(null);
      setAnswers({});
      try {
        const res = await api.post(`/resumes/${resumeId}/evidence-followup/questions`, {
          entry_type: entryType,
          index: entryIndex,
        });
        if (cancelled) return;
        setContext(res.data.context);
        setQuestions(res.data.questions || []);
      } catch (err) {
        if (!cancelled) {
          message.error(err.response?.data?.detail || '加载追问失败');
          onClose?.();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [open, resumeId, entryType, entryIndex, onClose]);

  const handleSubmit = async () => {
    const payload = questions.map((q) => ({
      id: q.id,
      question: q.question,
      answer: (answers[q.id] || '').trim(),
    })).filter((a) => a.answer);

    if (payload.length === 0) {
      message.warning('请至少回答一个问题');
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post(`/resumes/${resumeId}/evidence-followup/regenerate`, {
        entry_type: entryType,
        index: entryIndex,
        answers: payload,
      });
      setResult(res.data);
      setStep(1);
      message.success('已生成带量化指标的证据句');
    } catch (err) {
      message.error(err.response?.data?.detail || '生成失败');
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
      suggested_text: result.example_after,
      original_text: result.example_before,
    });
    onClose?.();
  };

  return (
    <Modal
      title={<><QuestionCircleOutlined /> AI 证据追问</>}
      open={open}
      onCancel={onClose}
      width={560}
      footer={null}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16, fontSize: 13 }}
        message="检测到该段经历缺少量化数据"
        description="请补充真实数据，系统将生成带数字的证据句（不会编造您未提供的信息）"
      />

      <Steps
        size="small"
        current={step}
        style={{ marginBottom: 16 }}
        items={[
          { title: '回答追问' },
          { title: '预览证据句' },
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
                padding: '8px 12px',
                background: '#fef2f2',
                borderRadius: 8,
                marginBottom: 12,
                fontSize: 13,
              }}
              >
                原文：{context.example_before}
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
                    placeholder="请输入真实数据…"
                  />
                </Form.Item>
              ))}
            </Form>

            <Space style={{ marginTop: 8 }}>
              <Button onClick={onClose}>取消</Button>
              <Button type="primary" loading={submitting} onClick={handleSubmit}>
                生成证据句
              </Button>
            </Space>
          </>
        )}

        {step === 1 && result && (
          <>
            <Text type="secondary" style={{ fontSize: 12 }}>改写后（含量化指标）</Text>
            <div style={{
              padding: '12px',
              background: '#ecfdf5',
              border: '1px solid #a7f3d0',
              borderRadius: 8,
              marginTop: 8,
              marginBottom: 16,
              fontSize: 14,
              lineHeight: 1.7,
            }}
            >
              {result.example_after}
            </div>
            {!result.has_quantification && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="生成内容可能仍缺数字，建议补充更多具体数据后重试"
              />
            )}
            <Space>
              <Button onClick={() => setStep(0)}>返回修改</Button>
              <Button type="primary" onClick={handleApply}>
                采纳到简历
              </Button>
            </Space>
          </>
        )}
      </Spin>
    </Modal>
  );
}

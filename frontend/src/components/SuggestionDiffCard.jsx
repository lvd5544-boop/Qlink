import { useCallback, useState, useEffect } from 'react';
import { Card, Button, Space, Tag, Typography, Input, Spin } from 'antd';
import { CheckOutlined, CloseOutlined, EditOutlined, RiseOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import api from '../api';
import EvidenceFollowupModal from './EvidenceFollowupModal';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const PLACEHOLDER_HINTS = ['需先完成', '待补充', '待填写', '证据追问', '填入真实数据后再'];

function isPlaceholderText(text) {
  const t = (text || '').trim();
  if (!t) return true;
  return PLACEHOLDER_HINTS.some((h) => t.includes(h));
}

/**
 * 建议卡片：原文与修改版对照，预览 score_delta，可编辑后采纳。
 * 不得把 append_quantification 静默改成 fill_field；未完成证据时禁用采纳。
 */
export default function SuggestionDiffCard({
  suggestion,
  resumeId,
  onAccept,
  onDismiss,
  loading = false,
}) {
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState(suggestion.suggested_text || '');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [followupOpen, setFollowupOpen] = useState(false);
  const [evidenceReady, setEvidenceReady] = useState(false);

  const entryType = suggestion.entry_type
    || (suggestion.patch?.section === 'projects' ? 'project' : 'work');
  const entryIndex = suggestion.entry_index ?? suggestion.patch?.index;
  const storedAction = suggestion.patch?.action || 'fill_field';
  const needsEvidence = Boolean(
    suggestion.requires_evidence
    || suggestion.needs_followup
    || storedAction === 'append_quantification'
  );
  const showFollowup = needsEvidence;
  const blockedByEvidence = needsEvidence && !evidenceReady;
  const displayText = editedText || suggestion.suggested_text || '';
  const acceptBlocked = blockedByEvidence || isPlaceholderText(displayText);

  /**
   * 保留存储的 action；仅在非量化建议时允许用编辑后的全文更新 value。
   * append_quantification：value 为证据片段，不得改成 fill_field。
   */
  const buildPatch = useCallback((finalText, { evidenceCompleted = false } = {}) => {
    const patch = { ...suggestion.patch };
    const text = (finalText || '').trim();

    if (storedAction === 'append_quantification') {
      patch.action = 'append_quantification';
      patch.value = text;
      if (evidenceCompleted) {
        patch.evidence_completed = true;
      }
      return patch;
    }

    if (patch.section === 'work_experience' && patch.index != null) {
      patch.action = patch.action || 'fill_field';
      patch.field = patch.field || 'description';
      patch.value = text;
    } else if (patch.section === 'projects' && patch.index != null) {
      patch.action = patch.action || 'fill_field';
      patch.field = patch.field || 'description';
      patch.value = text;
    } else if (patch.section === 'summary') {
      patch.action = patch.action || 'fill_field';
      patch.value = text;
    } else if (patch.section === 'basic' && patch.field) {
      patch.action = patch.action || 'fill_field';
      patch.value = text;
    } else if (patch.section === 'skills') {
      const parts = text.split(/[、,，]/).map((s) => s.trim()).filter(Boolean);
      patch.value = parts[parts.length - 1] || text;
    } else if (patch.action === 'add_project') {
      patch.value = {
        ...(patch.value || {}),
        description: text,
      };
    }
    return patch;
  }, [storedAction, suggestion.patch]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setEditedText(suggestion.suggested_text || '');
      setEditing(false);
      setEvidenceReady(false);
    }, 0);
    return () => clearTimeout(timer);
  }, [suggestion.id, suggestion.suggested_text]);

  useEffect(() => {
    if (!resumeId) return undefined;
    if (acceptBlocked && !evidenceReady) {
      const blockedTimer = setTimeout(() => setPreview(null), 0);
      return () => clearTimeout(blockedTimer);
    }
    let cancelled = false;

    const runPreview = async () => {
      setPreviewLoading(true);
      try {
        const patch = buildPatch(editedText || suggestion.suggested_text || '', {
          evidenceCompleted: evidenceReady,
        });
        if (isPlaceholderText(patch.value) && storedAction === 'append_quantification') {
          if (!cancelled) setPreview(null);
          return;
        }
        const res = await api.post(`/resumes/${resumeId}/preview-suggestion`, { patch });
        if (!cancelled) setPreview(res.data);
      } catch {
        if (!cancelled) setPreview(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };

    const timer = setTimeout(runPreview, editing ? 500 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    resumeId,
    suggestion.id,
    editedText,
    editing,
    suggestion.suggested_text,
    evidenceReady,
    acceptBlocked,
    buildPatch,
    storedAction,
  ]);

  const handleAccept = () => {
    if (acceptBlocked) return;
    const finalText = (editedText || suggestion.suggested_text || '').trim();
    if (isPlaceholderText(finalText)) return;
    const patch = buildPatch(finalText, { evidenceCompleted: evidenceReady });
    onAccept({ ...suggestion, patch, suggested_text: finalText });
  };

  const handleFollowupRegenerated = (regenerated) => {
    const finalText = regenerated.example_after;
    setEditedText(finalText);
    setEditing(false);
    setEvidenceReady(true);
    const patch = buildPatch(finalText, { evidenceCompleted: true });
    patch.fidelity_result = regenerated.patch?.fidelity_result || regenerated.fidelity_result;
    patch.evidence_references = regenerated.patch?.evidence_references || regenerated.evidence_references;
    patch.fidelity_proof = regenerated.fidelity_proof || regenerated.patch?.fidelity_proof;
    onAccept({
      ...suggestion,
      ...regenerated,
      patch,
      suggested_text: finalText,
      original_text: regenerated.example_before,
      requires_evidence: false,
      needs_followup: false,
    });
  };

  const original = suggestion.original_text || '（空）';
  const isEmptyOriginal = original === '（空）' || original === '（暂无描述）' || original === '（暂无技能）';

  const matchDelta = preview?.score_delta;
  const healthDelta = preview?.health_score_delta;

  return (
    <Card
      size="small"
      style={{
        marginBottom: 12,
        border: '1px solid #e2e8f0',
        boxShadow: '0 1px 4px rgba(15,23,42,0.06)',
      }}
      styles={{ body: { padding: 14 } }}
    >
      <Space style={{ marginBottom: 10 }} wrap>
        <Tag color={suggestion.priority === '高' ? 'red' : 'blue'}>{suggestion.priority}</Tag>
        {suggestion.source === 'coach' && <Tag color="purple">Coach</Tag>}
        <Text strong>{suggestion.section_label || suggestion.title}</Text>
        {needsEvidence && !evidenceReady && <Tag color="orange">需先补充证据</Tag>}
        {previewLoading ? (
          <Spin size="small" />
        ) : (
          <>
            {matchDelta != null && matchDelta !== 0 && (
              <Tag color={matchDelta > 0 ? 'success' : 'warning'}>
                <RiseOutlined /> 匹配 {matchDelta > 0 ? '+' : ''}{matchDelta}
              </Tag>
            )}
            {healthDelta != null && healthDelta !== 0 && (
              <Tag color={healthDelta > 0 ? 'processing' : 'default'}>
                体检 {healthDelta > 0 ? '+' : ''}{healthDelta}
              </Tag>
            )}
          </>
        )}
      </Space>

      <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
        {suggestion.description}
      </Paragraph>

      {preview?.job_title && (
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
          对比岗位：{preview.job_title}
          {preview.old_score != null && (
            <> · 当前 {Number(preview.old_score).toFixed(1)} → 预计 {Number(preview.new_score).toFixed(1)}</>
          )}
        </Text>
      )}

      {!isEmptyOriginal && (
        <div style={{ marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            原文
          </Text>
          <div
            style={{
              padding: '10px 12px',
              borderRadius: 8,
              background: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#991b1b',
              fontSize: 14,
              lineHeight: 1.6,
              textDecoration: 'line-through',
              opacity: 0.9,
            }}
          >
            {original}
          </div>
        </div>
      )}

      <div>
        <Space style={{ marginBottom: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {blockedByEvidence
              ? '占位提示（不可写回）'
              : (isEmptyOriginal ? '建议填写' : '建议改为')}
          </Text>
          {!editing && !blockedByEvidence && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setEditedText(suggestion.suggested_text || '');
                setEditing(true);
              }}
            >
              编辑
            </Button>
          )}
        </Space>
        {editing ? (
          <TextArea
            rows={3}
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            style={{ marginBottom: 8 }}
          />
        ) : (
          <div
            style={{
              padding: '10px 12px',
              borderRadius: 8,
              background: blockedByEvidence ? '#fff7ed' : '#ecfdf5',
              border: blockedByEvidence ? '1px solid #fed7aa' : '1px solid #a7f3d0',
              color: blockedByEvidence ? '#9a3412' : '#065f46',
              fontSize: 14,
              lineHeight: 1.6,
            }}
          >
            {displayText}
          </div>
        )}
      </div>

      <Space style={{ marginTop: 12 }} wrap>
        {showFollowup && entryIndex != null && (
          <Button
            type={blockedByEvidence ? 'primary' : 'default'}
            size="small"
            icon={<QuestionCircleOutlined />}
            onClick={() => setFollowupOpen(true)}
          >
            先补充证据
          </Button>
        )}
        <Button
          type={blockedByEvidence ? 'default' : 'primary'}
          size="small"
          icon={<CheckOutlined />}
          loading={loading}
          disabled={acceptBlocked}
          onClick={handleAccept}
        >
          {blockedByEvidence ? '先补充证据' : `采纳${matchDelta > 0 ? ` (+${matchDelta})` : ''}`}
        </Button>
        <Button size="small" icon={<CloseOutlined />} onClick={() => onDismiss(suggestion)}>
          忽略
        </Button>
        {editing && (
          <Button size="small" onClick={() => setEditing(false)}>
            取消编辑
          </Button>
        )}
      </Space>

      <EvidenceFollowupModal
        open={followupOpen}
        onClose={() => setFollowupOpen(false)}
        resumeId={resumeId}
        entryType={entryType}
        entryIndex={entryIndex}
        onRegenerated={handleFollowupRegenerated}
      />
    </Card>
  );
}

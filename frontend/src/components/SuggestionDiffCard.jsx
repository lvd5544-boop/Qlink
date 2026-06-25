import { useState, useEffect } from 'react';
import { Card, Button, Space, Tag, Typography, Input, Spin } from 'antd';
import { CheckOutlined, CloseOutlined, EditOutlined, RiseOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import api from '../api';
import EvidenceFollowupModal from './EvidenceFollowupModal';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * 建议卡片：原文与修改版对照，预览 score_delta，可编辑后采纳。
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

  const entryType = suggestion.entry_type
    || (suggestion.patch?.section === 'projects' ? 'project' : 'work');
  const entryIndex = suggestion.entry_index ?? suggestion.patch?.index;
  const showFollowup = suggestion.needs_followup
    || suggestion.patch?.action === 'append_quantification';

  const buildPatch = (finalText) => {
    const patch = { ...suggestion.patch };
    if (patch.section === 'work_experience' && patch.index != null) {
      patch.action = 'fill_field';
      patch.field = 'description';
      patch.value = finalText;
    } else if (patch.section === 'projects' && patch.index != null) {
      patch.action = 'fill_field';
      patch.field = 'description';
      patch.value = finalText;
    } else if (patch.section === 'summary') {
      patch.action = 'fill_field';
      patch.value = finalText;
    } else if (patch.section === 'basic' && patch.field) {
      patch.action = 'fill_field';
      patch.value = finalText;
    } else if (patch.section === 'skills') {
      const parts = finalText.split(/[、,，]/).map((s) => s.trim()).filter(Boolean);
      patch.value = parts[parts.length - 1] || finalText;
    } else if (patch.action === 'add_project') {
      patch.value = {
        ...(patch.value || {}),
        description: finalText,
      };
    }
    return patch;
  };

  useEffect(() => {
    setEditedText(suggestion.suggested_text || '');
    setEditing(false);
  }, [suggestion.id, suggestion.suggested_text]);

  useEffect(() => {
    if (!resumeId) return undefined;
    let cancelled = false;

    const runPreview = async () => {
      setPreviewLoading(true);
      try {
        const patch = buildPatch(editedText || suggestion.suggested_text || '');
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
  }, [resumeId, suggestion.id, editedText, editing, suggestion.suggested_text]);

  const handleAccept = () => {
    const finalText = (editedText || suggestion.suggested_text || '').trim();
    const patch = buildPatch(finalText);
    onAccept({ ...suggestion, patch, suggested_text: finalText });
  };

  const handleFollowupRegenerated = (regenerated) => {
    const finalText = regenerated.example_after;
    setEditedText(finalText);
    setEditing(false);
    const patch = buildPatch(finalText);
    onAccept({
      ...suggestion,
      ...regenerated,
      patch,
      suggested_text: finalText,
      original_text: regenerated.example_before,
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
            {isEmptyOriginal ? '建议填写' : '建议改为'}
          </Text>
          {!editing && (
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
              background: '#ecfdf5',
              border: '1px solid #a7f3d0',
              color: '#065f46',
              fontSize: 14,
              lineHeight: 1.6,
            }}
          >
            {editedText || suggestion.suggested_text}
          </div>
        )}
      </div>

      <Space style={{ marginTop: 12 }} wrap>
        {showFollowup && entryIndex != null && (
          <Button
            size="small"
            icon={<QuestionCircleOutlined />}
            onClick={() => setFollowupOpen(true)}
          >
            AI 追问补充
          </Button>
        )}
        <Button
          type="primary"
          size="small"
          icon={<CheckOutlined />}
          loading={loading}
          onClick={handleAccept}
        >
          采纳
          {matchDelta > 0 ? ` (+${matchDelta})` : ''}
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

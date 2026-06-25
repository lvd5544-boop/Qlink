import { useEffect, useState, useCallback } from 'react';
import {
  Card, List, Button, Modal, Tag, Space, message, Spin, Row, Col, Typography, Divider,
} from 'antd';
import {
  EditOutlined, DeleteOutlined, MedicineBoxOutlined, StarOutlined, ArrowLeftOutlined,
} from '@ant-design/icons';
import api from '../../api';
import ResumeHealthPanel from '../../components/ResumeHealthPanel';
import ResumeDocumentView from '../../components/ResumeDocumentView';
import ResumeEditForm from '../../components/ResumeEditForm';
import ResumeCoachPanel from '../../components/ResumeCoachPanel';
import { notifyDashboardRefresh } from '../../utils/dashboardSync';

const { Text, Paragraph } = Typography;

function initEditData(resume) {
  const data = JSON.parse(JSON.stringify(resume.parsed || {}));
  data.skills = data.skills || [];
  data.work_experience = data.work_experience || [];
  data.projects = data.projects || [];
  data.soft_skills = data.soft_skills || [];
  return data;
}

export default function MyResumes() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [editData, setEditData] = useState({});
  const [rawText, setRawText] = useState('');
  const [topMatches, setTopMatches] = useState([]);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [healthLoadingId, setHealthLoadingId] = useState(null);
  const [applyingId, setApplyingId] = useState(null);
  const [pendingSuggestions, setPendingSuggestions] = useState([]);
  const [saving, setSaving] = useState(false);

  const userId = localStorage.getItem('user_id');
  const selectedResume = resumes.find((r) => r.id === selectedId) || null;

  const fetchResumes = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/resumes/${userId}`);
      setResumes(res.data);
    } catch {
      message.error('加载简历列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchResumes(); }, []);

  const fetchTopMatches = useCallback(async (resumeId) => {
    setMatchesLoading(true);
    try {
      const res = await api.get(`/matches/resume/${resumeId}`);
      setTopMatches((res.data || []).slice(0, 3));
    } catch {
      setTopMatches([]);
    } finally {
      setMatchesLoading(false);
    }
  }, []);

  const fetchPendingSuggestions = useCallback(async (resumeId) => {
    try {
      const res = await api.get(`/resumes/${resumeId}/suggestions`);
      setPendingSuggestions(res.data?.suggestions || []);
    } catch {
      setPendingSuggestions([]);
    }
  }, []);

  const openWorkbench = async (resume) => {
    setSelectedId(resume.id);
    setEditData(initEditData(resume));
    setPendingSuggestions([]);
    setRawText('');
    setTopMatches([]);
    try {
      const detail = await api.get(`/resume/${resume.id}`);
      const merged = { ...resume, ...detail.data };
      setResumes((prev) => prev.map((r) => (r.id === resume.id ? merged : r)));
      setEditData(initEditData(merged));
      setRawText(detail.data.raw_text || '');
      if (!merged.health_check) {
        await handleRefreshHealth(resume.id, false);
      } else {
        await fetchPendingSuggestions(resume.id);
      }
    } catch {
      message.warning('未能加载简历详情');
    }
    await fetchTopMatches(resume.id);
  };

  const closeWorkbench = () => {
    setSelectedId(null);
    setEditData({});
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const res = await api.put(`/resumes/${selectedId}`, { parsed_json: editData });
      message.success('保存成功，已重新体检并更新匹配分');
      if (res.data?.top_match?.score != null) {
        message.info(`最高匹配：${res.data.top_match.job_title} ${res.data.top_match.score} 分`);
      }
      if (res.data?.dashboard_indicators) {
        notifyDashboardRefresh({ indicators: res.data.dashboard_indicators });
      }
      await fetchResumes();
      if (res.data?.health_check) {
        setResumes((prev) => prev.map((r) => (
          r.id === selectedId
            ? { ...r, parsed: editData, health_check: res.data.health_check }
            : r
        )));
      }
      await fetchTopMatches(selectedId);
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshHealth = async (resumeId, showMsg = true) => {
    setHealthLoadingId(resumeId);
    try {
      const res = await api.post(`/resumes/${resumeId}/health-check`);
      const updated = res.data.health_check;
      setResumes((prev) => prev.map((r) => (
        r.id === resumeId ? { ...r, health_check: updated } : r
      )));
      await fetchPendingSuggestions(resumeId);
      if (showMsg) message.success('体检已更新');
    } catch {
      message.error('体检失败');
    } finally {
      setHealthLoadingId(null);
    }
  };

  const handleDismissSuggestion = async (resumeId, suggestion) => {
    try {
      const res = await api.post(`/resumes/${resumeId}/dismiss-suggestion`, {
        suggestion_id: suggestion.db_id,
        suggestion_key: suggestion.id,
      });
      setPendingSuggestions(res.data?.pending_suggestions || []);
    } catch {
      setPendingSuggestions((prev) => prev.filter((s) => s.id !== suggestion.id));
    }
  };

  const handleApplySuggestion = async (resumeId, suggestion) => {
    setApplyingId(suggestion.id);
    try {
      const res = await api.post(`/resumes/${resumeId}/apply-suggestion`, {
        patch: suggestion.patch,
        suggestion_id: suggestion.db_id,
        suggestion_key: suggestion.id,
        job_id: suggestion.job_id,
      });
      message.success(
        `已采纳：匹配 ${res.data.score_delta > 0 ? `+${res.data.score_delta}` : '持平'}，体检 ${res.data.health_score_delta > 0 ? `+${res.data.health_score_delta}` : '持平'}`
      );
      notifyDashboardRefresh({
        score_delta: res.data.score_delta,
        health_score_delta: res.data.health_score_delta,
        completeness_delta: res.data.completeness_delta,
        indicators: res.data.dashboard_indicators,
      });
      setPendingSuggestions(res.data.pending_suggestions || []);
      setEditData(res.data.parsed_json);
      setResumes((prev) => prev.map((r) => (
        r.id === resumeId
          ? { ...r, parsed: res.data.parsed_json, health_check: res.data.health_check }
          : r
      )));
      await fetchTopMatches(resumeId);
    } catch {
      message.error('采纳失败');
    } finally {
      setApplyingId(null);
    }
  };

  const handleDelete = (resumeId) => {
    Modal.confirm({
      title: '确认删除',
      content: '删除后无法恢复，确定要删除这份简历吗？',
      onOk: async () => {
        try {
          await api.delete(`/resumes/${resumeId}`);
          message.success('删除成功');
          if (selectedId === resumeId) closeWorkbench();
          fetchResumes();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  const healthScore = (item) => item.health_check?.overall_score;

  const highlightSections = [];
  pendingSuggestions.forEach((s) => {
    if (s.patch?.section === 'summary') highlightSections.push('summary');
    if (s.patch?.section === 'skills') highlightSections.push('skills');
    if (s.patch?.section === 'education') highlightSections.push('education');
    if (s.patch?.section === 'work_experience' && s.patch?.index != null) {
      highlightSections.push(`work_${s.patch.index}`);
    }
    if (s.patch?.section === 'projects' && s.patch?.index != null) {
      highlightSections.push(`project_${s.patch.index}`);
    }
  });

  const workbench = selectedResume && (
    <div style={{ marginTop: 16 }}>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={closeWorkbench}>返回列表</Button>
        <Button
          icon={<MedicineBoxOutlined />}
          loading={healthLoadingId === selectedResume.id}
          onClick={() => handleRefreshHealth(selectedResume.id)}
        >
          重新体检
        </Button>
        <Tag color={healthScore(selectedResume) >= 70 ? 'success' : 'warning'}>
          体检 {healthScore(selectedResume) ?? '—'} 分
        </Tag>
      </Space>

      <Row gutter={16}>
        {/* 左栏：编辑 */}
        <Col xs={24} lg={6}>
          <Card size="small" title="① 编辑" styles={{ body: { maxHeight: '75vh', overflowY: 'auto' } }}>
            <ResumeEditForm
              data={editData}
              onChange={setEditData}
              onSave={handleSave}
              saving={saving}
            />
          </Card>
        </Col>

        {/* 中栏：实时预览 */}
        <Col xs={24} lg={9}>
          <Card size="small" title="② 实时预览" styles={{ body: { maxHeight: '75vh', overflowY: 'auto' } }}>
            <ResumeDocumentView parsed={editData} highlightSections={highlightSections} />
            {rawText && (
              <>
                <Divider style={{ margin: '12px 0' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>上传原文摘录</Text>
                <Paragraph
                  style={{
                    fontSize: 12,
                    color: '#64748b',
                    background: '#f8fafc',
                    padding: 8,
                    borderRadius: 6,
                    maxHeight: 120,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {rawText.slice(0, 800)}{rawText.length > 800 ? '…' : ''}
                </Paragraph>
              </>
            )}
            <Divider style={{ margin: '12px 0' }} />
            <Text strong><StarOutlined /> Top 3 匹配</Text>
            <Spin spinning={matchesLoading}>
              {topMatches.length === 0 ? (
                <Text type="secondary" style={{ fontSize: 12 }}>保存或采纳建议后更新</Text>
              ) : (
                <List
                  size="small"
                  dataSource={topMatches}
                  renderItem={(m, idx) => (
                    <List.Item style={{ padding: '4px 0' }}>
                      <Tag color={idx === 0 ? 'gold' : 'blue'}>#{idx + 1}</Tag>
                      <Text style={{ fontSize: 13 }}>{m.job_title}</Text>
                      <Tag color="volcano">{Number(m.score).toFixed(1)}</Tag>
                    </List.Item>
                  )}
                />
              )}
            </Spin>
          </Card>
        </Col>

        {/* 右栏：诊断 + 建议 + Coach */}
        <Col xs={24} lg={9}>
          <div style={{ maxHeight: '75vh', overflowY: 'auto' }}>
            <Card size="small" title="③ 诊断与采纳" style={{ marginBottom: 12 }}>
              <ResumeHealthPanel
                healthCheck={selectedResume.health_check}
                actionableSuggestions={pendingSuggestions}
                resumeId={selectedResume.id}
                onApplySuggestion={(s) => handleApplySuggestion(selectedResume.id, s)}
                onDismissSuggestion={(s) => handleDismissSuggestion(selectedResume.id, s)}
                applyingId={applyingId}
              />
            </Card>
            <ResumeCoachPanel
              resumeId={selectedResume.id}
              defaultJobTitle={editData.expected_job_title}
              onApplySuggestion={(s) => handleApplySuggestion(selectedResume.id, s)}
              onDismissSuggestion={(s) => handleDismissSuggestion(selectedResume.id, s)}
              onSuggestionsUpdated={setPendingSuggestions}
              applyingId={applyingId}
            />
          </div>
        </Col>
      </Row>
    </div>
  );

  return (
    <Card className="content-card" title="我的简历 · AI 工作台">
      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        诊断、编辑、预览、采纳在同一页完成，无需跳转数据分析页
      </Paragraph>

      <Spin spinning={loading}>
        {!selectedId ? (
          <List
            dataSource={resumes}
            renderItem={(item) => (
              <List.Item
                extra={(
                  <Space>
                    <Button type="primary" icon={<EditOutlined />} onClick={() => openWorkbench(item)}>
                      进入工作台
                    </Button>
                    <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(item.id)} />
                  </Space>
                )}
              >
                <List.Item.Meta
                  title={(
                    <Space>
                      <span>{item.parsed?.name ? `${item.parsed.name} 的简历` : '未命名简历'}</span>
                      {healthScore(item) != null ? (
                        <Tag color={healthScore(item) >= 70 ? 'success' : 'warning'}>
                          体检 {healthScore(item)} 分
                        </Tag>
                      ) : (
                        <Tag>未体检</Tag>
                      )}
                    </Space>
                  )}
                  description={(
                    <span>
                      期望职位：{item.parsed?.expected_job_title || '无'} ·
                      上传：{new Date(item.uploaded_at).toLocaleString()}
                    </span>
                  )}
                />
              </List.Item>
            )}
            locale={{ emptyText: '暂无简历，请先上传' }}
          />
        ) : (
          workbench
        )}
      </Spin>
    </Card>
  );
}

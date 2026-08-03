import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card, List, Button, Modal, Tag, Space, message, Spin, Row, Col, Typography, Divider, Alert,
} from 'antd';
import {
  EditOutlined, DeleteOutlined, MedicineBoxOutlined, ArrowLeftOutlined,
} from '@ant-design/icons';
import api from '../../api';
import ResumeHealthPanel from '../../components/ResumeHealthPanel';
import ResumeDocumentView from '../../components/ResumeDocumentView';
import ResumeEditForm from '../../components/ResumeEditForm';
import ResumeCoachPanel from '../../components/ResumeCoachPanel';
import ResumeVariantsPanel from '../../components/ResumeVariantsPanel';
import ClaimPassportPanel from '../../components/ClaimPassportPanel';
import ImprovementSimulationPanel from '../../components/ImprovementSimulationPanel';
import TargetJobOptimizationPanel from '../../components/TargetJobOptimizationPanel';
import TopJobMatches from '../../components/TopJobMatches';
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
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const deepLinkHandled = useRef(false);
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [editData, setEditData] = useState({});
  const [rawText, setRawText] = useState('');
  const [topMatches, setTopMatches] = useState([]);
  const [targetJobId, setTargetJobId] = useState(null);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [healthLoadingId, setHealthLoadingId] = useState(null);
  const [applyingId, setApplyingId] = useState(null);
  const [pendingSuggestions, setPendingSuggestions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [claimHint, setClaimHint] = useState('');
  const [passportFocus, setPassportFocus] = useState(null);

  const userId = localStorage.getItem('user_id');
  const selectedResume = resumes.find((r) => r.id === selectedId) || null;
  const targetJob = topMatches.find((item) => String(item.job_id) === String(targetJobId)) || null;

  const handleTargetJobChange = useCallback((matchOrJob) => {
    const nextId = matchOrJob?.job_id || matchOrJob?.id || null;
    setTargetJobId(nextId);
  }, []);

  const handleSimulationAction = useCallback((option, issue) => {
    if (option.next_action === 'view_alternative_roles') {
      navigate('/candidate/browse-jobs');
      return;
    }
    if (option.next_action === 'preview_rewrite') {
      document.getElementById('resume-coach')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      message.info('已定位到 AI 简历诊断，请基于现有事实预览改写');
      return;
    }
    const hasClaims = Boolean(issue.claim_ids?.length);
    setPassportFocus({
      requestId: `${Date.now()}-${option.strategy_id}`,
      claimIds: issue.claim_ids || [],
      title: option.next_action === 'open_evidence_followup' ? '补充证据' : '查看相关履历主张',
      message: hasClaims
        ? `${issue.diagnosis} 已展开相关主张，请填写背景、角色、指标口径或文档引用。`
        : `${issue.diagnosis} 当前问题未关联到现有主张；请先在“① 编辑”补充真实项目或经历，保存后再同步主张。`,
    });
    requestAnimationFrame(() => {
      document.getElementById('claim-passport')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [navigate]);

  const handleResumeEnriched = useCallback((parsed) => {
    if (!selectedId || !parsed) return;
    setEditData(parsed);
    setResumes((previous) => previous.map((resume) => (
      resume.id === selectedId ? { ...resume, parsed } : resume
    )));
  }, [selectedId]);

  const fetchResumes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/resumes/${userId}`);
      setResumes(res.data);
    } catch {
      message.error('加载简历列表失败');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    const timer = setTimeout(fetchResumes, 0);
    return () => clearTimeout(timer);
  }, [fetchResumes]);

  useEffect(() => {
    const hint = searchParams.get('claimHint');
    if (!hint) return undefined;
    const timer = setTimeout(() => setClaimHint(hint), 0);
    return () => clearTimeout(timer);
  }, [searchParams]);

  const fetchTopMatches = useCallback(async (resumeId) => {
    setMatchesLoading(true);
    try {
      const res = await api.get(`/matches/resume/${resumeId}`);
      const rows = (res.data || []).slice(0, 3);
      setTopMatches(rows);
      setTargetJobId((current) => (
        rows.some((item) => String(item.job_id) === String(current))
          ? current
          : (rows[0]?.job_id || null)
      ));
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

  const handleRefreshHealth = useCallback(async (resumeId, showMsg = true) => {
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
  }, [fetchPendingSuggestions]);

  const openWorkbench = useCallback(async (resume) => {
    setSelectedId(resume.id);
    setEditData(initEditData(resume));
    setPendingSuggestions([]);
    setRawText('');
    setTopMatches([]);
    setTargetJobId(null);
    try {
      const detail = await api.get(`/resume/${resume.id}`);
      const merged = { ...resume, ...detail.data };
      setResumes((prev) => prev.map((r) => (r.id === resume.id ? merged : r)));
      setEditData(initEditData(merged));
      setRawText(detail.data.raw_text || '');
      const needsConsistencyRefresh = !merged.health_check?.consistency_diagnosis;
      if (!merged.health_check || needsConsistencyRefresh) {
        await handleRefreshHealth(resume.id, needsConsistencyRefresh);
      } else {
        await fetchPendingSuggestions(resume.id);
      }
    } catch {
      message.warning('未能加载简历详情');
    }
    await fetchTopMatches(resume.id);
  }, [fetchPendingSuggestions, fetchTopMatches, handleRefreshHealth]);

  useEffect(() => {
    if (loading || deepLinkHandled.current || selectedId) return undefined;
    const timer = setTimeout(() => {
      const resumeId = searchParams.get('resumeId');
      if (!resumeId) return;

      deepLinkHandled.current = true;
      setSearchParams({}, { replace: true });

      if (!resumes.length) {
        message.warning('暂无简历，请先上传');
        return;
      }

      const target = resumes.find((r) => r.id === resumeId);
      if (target) {
        openWorkbench(target);
        const hint = searchParams.get('claimHint');
        if (hint) {
          setClaimHint(hint);
          message.info(`已打开简历。请在右侧「③ 诊断与采纳」查看表述一致性提醒：${hint.slice(0, 40)}…`);
        } else {
          message.info('已打开申请关联简历。在右侧「③ 诊断与采纳」可查看表述一致性提醒与 AI 追问。');
        }
      } else {
        message.warning('未找到对应简历，请从列表中选择');
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [loading, resumes, searchParams, selectedId, setSearchParams, openWorkbench]);

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

  const handleVariantApplied = async (data) => {
    if (!selectedId) return;
    setEditData(data.parsed_json);
    setResumes((prev) => prev.map((r) => (
      r.id === selectedId
        ? { ...r, parsed: data.parsed_json, health_check: data.health_check }
        : r
    )));
    if (data.dashboard_indicators) {
      notifyDashboardRefresh({ indicators: data.dashboard_indicators });
    }
    await fetchTopMatches(selectedId);
    await fetchPendingSuggestions(selectedId);
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
            <TopJobMatches
              matches={topMatches}
              loading={matchesLoading}
              targetJobId={targetJobId}
              onTargetChange={handleTargetJobChange}
            />
          </Card>
        </Col>

        {/* 右栏：诊断 + 建议 + Coach */}
        <Col xs={24} lg={9}>
          <div style={{ maxHeight: '75vh', overflowY: 'auto' }}>
            <Card size="small" title="③ 诊断与采纳" style={{ marginBottom: 12 }}>
              {claimHint && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="招聘方澄清相关 claim"
                  description={(
                    <>
                      <div style={{ marginBottom: 8 }}>{claimHint}</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        建议：先查看「表述一致性提醒」，再使用 AI 追问 / 忠实改写，把澄清内容沉淀进对应经历描述。
                      </Text>
                    </>
                  )}
                  closable
                  onClose={() => setClaimHint('')}
                />
              )}
              <ResumeHealthPanel
                healthCheck={selectedResume.health_check}
                actionableSuggestions={pendingSuggestions}
                resumeId={selectedResume.id}
                onApplySuggestion={(s) => handleApplySuggestion(selectedResume.id, s)}
                onDismissSuggestion={(s) => handleDismissSuggestion(selectedResume.id, s)}
                applyingId={applyingId}
              />
            </Card>
            <div id="resume-coach"><ResumeCoachPanel
              resumeId={selectedResume.id}
              defaultJobTitle={targetJob?.job_title || editData.expected_job_title}
              onApplySuggestion={(s) => handleApplySuggestion(selectedResume.id, s)}
              onDismissSuggestion={(s) => handleDismissSuggestion(selectedResume.id, s)}
              onSuggestionsUpdated={setPendingSuggestions}
              applyingId={applyingId}
            /></div>
            <ResumeVariantsPanel
              resumeId={selectedResume.id}
              defaultJobTitle={targetJob?.job_title || editData.expected_job_title}
              topMatches={topMatches}
              targetJobId={targetJobId}
              onTargetJobChange={handleTargetJobChange}
              onApplyVariant={handleVariantApplied}
            />
            <div id="claim-passport"><ClaimPassportPanel
              resumeId={selectedResume.id}
              focusRequest={passportFocus}
              onResumeEnriched={handleResumeEnriched}
            /></div>
            <ImprovementSimulationPanel
              resumeId={selectedResume.id}
              jobId={targetJobId}
              onAction={handleSimulationAction}
            />
          </div>
        </Col>
      </Row>
      <TargetJobOptimizationPanel
        key={`${selectedResume.id}:${targetJobId || 'none'}`}
        resumeId={selectedResume.id}
        targetJobId={targetJobId}
        onTargetJobChange={handleTargetJobChange}
        onApplied={() => openWorkbench(selectedResume)}
        onFocusClaims={(issue) => {
          setPassportFocus({
            requestId: `${Date.now()}-target-gap`,
            claimIds: issue.claim_ids || [],
            title: '已定位到岗位差距对应的经历',
            message: issue.diagnosis,
          });
          requestAnimationFrame(() => {
            document.getElementById('claim-passport')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
        }}
      />
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

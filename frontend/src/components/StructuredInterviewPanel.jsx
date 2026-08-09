import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Checkbox, Collapse, Divider, Input, List, Progress,
  Segmented, Select, Space, Tag, Typography, Upload, message,
} from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';

const { Text, Paragraph } = Typography;

const MODES = [
  { value: 'vault_builder', label: '构建职业记忆' },
  { value: 'target_gap', label: '补目标岗位信息' },
  { value: 'claim_clarification', label: '澄清 Claim' },
  { value: 'practice', label: '模拟面试（不写回）' },
];

function InterviewFeedback({ report }) {
  if (!report) return null;
  const coaching = report.personalized_coaching || {};
  const basis = coaching.personalization_basis || {};
  return (
    <Card size="small" title="AI 面试反馈">
      <Alert type="info" showIcon message={report.summary} description={report.disclaimer} />
      <Space wrap style={{ marginTop: 10 }}>
        {basis.anchor_experience && <Tag color="blue">重点经历：{basis.anchor_experience}</Tag>}
        {basis.target_role && <Tag color="purple">目标岗位：{basis.target_role}</Tag>}
        {basis.target_skill && <Tag color="cyan">重点能力：{basis.target_skill}</Tag>}
      </Space>
      <Space direction="vertical" style={{ width: '100%', marginTop: 12 }}>
        {Object.entries(report.scores || {}).map(([label, score]) => (
          <div key={label}>
            <Text>{label}</Text>
            <Progress percent={Number(score || 0)} size="small" />
          </div>
        ))}
      </Space>
      <Divider />
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text strong>优势</Text>
          <List
            size="small"
            dataSource={report.strengths || []}
            locale={{ emptyText: '本次回答还没有形成足够清晰的优势证据' }}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={item.title}
                  description={(
                    <Space direction="vertical" size={4}>
                      <Text>你的依据：“{item.evidence}”</Text>
                      {item.why_it_matters && <Text type="secondary">为什么重要：{item.why_it_matters}</Text>}
                      {item.keep_doing && <Text type="success">继续这样做：{item.keep_doing}</Text>}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        </div>
        <div>
          <Text strong>薄弱点</Text>
          <List
            size="small"
            dataSource={report.gaps || []}
            locale={{ emptyText: '未发现明显表达缺口' }}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={item.title}
                  description={(
                    <Space direction="vertical" size={4}>
                      <Text>{item.detail}</Text>
                      {item.impact && <Text type="warning">可能影响：{item.impact}</Text>}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        </div>
        <div>
          <Text strong>你的个性化训练计划</Text>
          {coaching.north_star && (
            <Alert
              style={{ marginTop: 8, marginBottom: 10 }}
              type="success"
              showIcon
              message="本轮训练主线"
              description={coaching.north_star}
            />
          )}
          {(report.recurring_patterns || []).length > 0 && (
            <Alert
              style={{ marginBottom: 10 }}
              type="warning"
              showIcon
              message="跨次面试反复出现的模式"
              description={report.recurring_patterns.map((item) => item.label).join('、')}
            />
          )}
          {(coaching.actions || []).length > 0 ? (
            <Collapse
              size="small"
              items={coaching.actions.map((item, index) => ({
                key: item.key || String(index),
                label: `${index + 1}. ${item.title} · ${item.estimated_effort}`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <Text>{item.why}</Text>
                    <Text type="secondary">基于你的材料：{item.based_on}</Text>
                    <div>
                      <Text strong>怎么练</Text>
                      <ol style={{ marginTop: 6, paddingLeft: 22 }}>
                        {(item.steps || []).map((step) => <li key={step}>{step}</li>)}
                      </ol>
                    </div>
                    <Alert type="info" message="马上练一遍" description={item.practice_prompt} />
                    <div>
                      <Text strong>做到什么算完成</Text>
                      <ul style={{ marginTop: 6, paddingLeft: 22 }}>
                        {(item.success_criteria || []).map((criterion) => <li key={criterion}>{criterion}</li>)}
                      </ul>
                    </div>
                  </Space>
                ),
              }))}
            />
          ) : (
            <List
              size="small"
              dataSource={report.improvements || []}
              renderItem={(item, index) => <List.Item>{index + 1}. {item}</List.Item>}
            />
          )}
        </div>
      </Space>
      <Collapse
        size="small"
        items={[{
          key: 'transcript',
          label: `查看完整问答记录（${report.transcript?.length || 0} 题）`,
          children: (
            <List
              size="small"
              dataSource={report.transcript || []}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={`${item.sequence_no}. ${item.question_text}`}
                    description={item.answer_text || (item.declined ? `已拒答：${item.decline_reason || ''}` : '未回答')}
                  />
                </List.Item>
              )}
            />
          ),
        }]}
      />
    </Card>
  );
}

export default function StructuredInterviewPanel() {
  const [entryContext] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return {
      mode: MODES.some((item) => item.value === params.get('mode')) ? params.get('mode') : 'vault_builder',
      resumeId: params.get('resumeId'),
      jobId: params.get('jobId'),
      jobTitle: params.get('jobTitle'),
    };
  });
  const [mode, setMode] = useState(entryContext.mode);
  const [resumeId, setResumeId] = useState(entryContext.resumeId);
  const [jobId, setJobId] = useState(entryContext.jobId);
  const [claimId, setClaimId] = useState(null);
  const [resumes, setResumes] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [claims, setClaims] = useState([]);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [consents, setConsents] = useState({
    resume_write: false,
    job_recommendation: false,
    employer_share: false,
    model_improvement: false,
  });
  const [session, setSession] = useState(null);
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [answer, setAnswer] = useState('');
  const [observations, setObservations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);

  const loadHistory = async () => {
    try {
      const response = await api.get('/interview-sessions?limit=20');
      setHistory(response.data?.sessions || []);
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    const userId = localStorage.getItem('user_id');
    if (!userId) return undefined;
    let cancelled = false;
    Promise.all([
      api.get(`/resumes/${userId}`).catch(() => ({ data: [] })),
      api.get('/browse-jobs').catch(() => ({ data: [] })),
      api.get('/career-passport/overview').catch(() => ({ data: {} })),
      api.get('/interview-sessions?limit=20').catch(() => ({ data: { sessions: [] } })),
    ]).then(([resumeResp, jobResp, overviewResp, historyResp]) => {
      if (cancelled) return;
      setResumes(resumeResp.data || []);
      const loadedJobs = Array.isArray(jobResp.data) ? jobResp.data : (jobResp.data?.jobs || []);
      if (entryContext.jobId && !loadedJobs.some((item) => String(item.id) === String(entryContext.jobId))) {
        loadedJobs.unshift({ id: entryContext.jobId, title: entryContext.jobTitle || '私有目标岗位' });
      }
      setJobs(loadedJobs);
      setClaims(overviewResp.data?.open_claims || []);
      setHistory(historyResp.data?.sessions || []);
    });
    return () => { cancelled = true; };
  }, [entryContext]);

  const refreshObservations = async (sessionId) => {
    const response = await api.get(`/interview-sessions/${sessionId}/observations`);
    setObservations(response.data?.observations || []);
  };

  const uploadResume = async (file) => {
    setUploadBusy(true);
    const body = new FormData();
    body.append('file', file);
    try {
      const response = await api.post('/parse-resume', body);
      const item = {
        id: response.data.resume_id,
        parsed: response.data,
      };
      setResumes((previous) => [item, ...previous.filter((resume) => resume.id !== item.id)]);
      setResumeId(item.id);
      message.success('简历已解析并选中，接下来会先建立问题清单');
    } catch (error) {
      message.error(getApiErrorMessage(error, '简历上传失败'));
    } finally {
      setUploadBusy(false);
    }
    return false;
  };

  const start = async () => {
    if (mode === 'claim_clarification' && !claimId) {
      message.warning('请选择要澄清的 Claim');
      return;
    }
    if (mode === 'target_gap' && !jobId) {
      message.warning('请选择目标岗位');
      return;
    }
    setBusy(true);
    try {
      const created = await api.post('/interview-sessions', {
        mode,
        resume_id: resumeId,
        job_id: jobId,
        claim_id: claimId,
        consent_snapshot: consents,
        ai_enabled: aiEnabled,
      });
      const nextSession = created.data.session;
      setSession(nextSession);
      const next = await api.post(`/interview-sessions/${nextSession.id}/next-question`);
      setCurrentQuestion(next.data.done ? null : next.data.question);
      setObservations([]);
      message.success('结构化面试会话已创建');
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建面试会话失败'));
    } finally {
      setBusy(false);
    }
  };

  const submitAnswer = async ({ declined = false, reason = null } = {}) => {
    if (!session || !currentQuestion) return;
    if (!declined && !answer.trim()) {
      message.warning('请填写回答，或选择拒答');
      return;
    }
    setBusy(true);
    try {
      const response = await api.post(`/interview-sessions/${session.id}/answers`, {
        question_id: currentQuestion.id,
        answer_text: declined ? null : answer.trim(),
        user_declined: declined,
        decline_reason: reason,
      });
      setObservations((prev) => [...prev, ...(response.data.observations || [])]);
      setAnswer('');
      if (reason === 'stop_followup') {
        setCurrentQuestion(null);
        message.info('已停止追问');
        return;
      }
      const next = await api.post(`/interview-sessions/${session.id}/next-question`);
      setCurrentQuestion(next.data.done ? null : next.data.question);
      const refreshed = await api.get(`/interview-sessions/${session.id}`);
      setSession(refreshed.data.session);
    } catch (error) {
      message.error(getApiErrorMessage(error, '提交回答失败'));
    } finally {
      setBusy(false);
    }
  };

  const resolveObservation = async (observationId, action) => {
    try {
      await api.post(`/interview-observations/${observationId}/${action}`);
      await refreshObservations(session.id);
      message.success(action === 'confirm' ? '已确认观察结果' : '已拒绝该观察结果');
    } catch (error) {
      message.error(getApiErrorMessage(error, '更新观察结果失败'));
    }
  };

  const exitSession = async (action) => {
    if (!session) return;
    try {
      const response = await api.post(`/interview-sessions/${session.id}/${action}`);
      if (action === 'complete') setSelectedReport(response.data?.report || null);
      setSession(null);
      setCurrentQuestion(null);
      setObservations([]);
      message.success(action === 'revoke' ? '会话已撤回' : '会话已完成');
      await loadHistory();
    } catch (error) {
      message.error(getApiErrorMessage(error, '结束会话失败'));
    }
  };

  const openHistory = async (item) => {
    try {
      const response = await api.get(`/interview-sessions/${item.id}`);
      setSelectedReport(response.data?.report || item.report || null);
    } catch (error) {
      message.error(getApiErrorMessage(error, '面试记录加载失败'));
    }
  };

  const progress = session?.progress || { answered_count: 0, question_total: 0 };
  const percent = progress.question_total
    ? Math.round((progress.answered_count / Math.max(progress.question_total, 1)) * 100)
    : 0;

  return (
    <Card title="结构化 AI 面试官" style={{ marginBottom: 16 }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="问题目标由规则选择；模型只负责表达。模拟面试默认不写回 Claim。"
      />
      {!session ? (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {entryContext.jobId && (
            <Alert
              type="success"
              showIcon
              message="已从机会准备卡带入本次目标岗位和简历"
              description="面试问题会使用同一份岗位要求与履历上下文。观察结果仍需要你逐条确认。"
            />
          )}
          <div>
            <Text type="secondary">面试模式</Text>
            <Segmented
              block
              options={MODES}
              value={mode}
              onChange={setMode}
              style={{ marginTop: 8 }}
            />
          </div>
          <Select
            allowClear
            placeholder="选择简历（可选）"
            style={{ width: '100%' }}
            value={resumeId}
            onChange={setResumeId}
            options={resumes.map((item) => ({
              value: item.id,
              label: item.parsed?.name || item.parsed_json?.basics?.name || `简历 ${String(item.id).slice(0, 8)}`,
            }))}
          />
          <Upload
            accept=".pdf,.docx,.txt"
            showUploadList={false}
            beforeUpload={uploadResume}
          >
            <Button icon={<UploadOutlined />} loading={uploadBusy}>
              直接上传一份简历并用于本次追问
            </Button>
          </Upload>
          {mode === 'target_gap' && (
            <Select
              placeholder="选择目标岗位"
              style={{ width: '100%' }}
              value={jobId}
              onChange={setJobId}
              options={jobs.map((item) => ({ value: item.id, label: item.title || item.id }))}
            />
          )}
          {mode === 'claim_clarification' && (
            <Select
              placeholder="选择要澄清的 Claim"
              style={{ width: '100%' }}
              value={claimId}
              onChange={setClaimId}
              options={claims.map((item) => ({ value: item.id, label: item.text || item.id }))}
            />
          )}
          <Checkbox checked={aiEnabled} onChange={(event) => setAiEnabled(event.target.checked)}>
            启用澄清追问（当前为规则题库；模型仅作自然语言增强）
          </Checkbox>
          <Space wrap>
            {Object.entries({
              resume_write: '简历写回',
              job_recommendation: '岗位推荐',
              employer_share: '分享给招聘方',
              model_improvement: '模型改进',
            }).map(([key, label]) => (
              <Checkbox
                key={key}
                checked={consents[key]}
                onChange={(event) => setConsents((prev) => ({ ...prev, [key]: event.target.checked }))}
              >
                {label}
              </Checkbox>
            ))}
          </Space>
          <Button type="primary" loading={busy} onClick={start}>开始结构化面试</Button>
        </Space>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space wrap>
            <Tag color="blue">{MODES.find((item) => item.value === session.mode)?.label || session.mode}</Tag>
            <Tag>{session.status}</Tag>
            <Text type="secondary">policy {session.policy_version}</Text>
          </Space>
          <Progress percent={percent} format={() => `${progress.answered_count}/${progress.question_total || '?'}`} />
          {currentQuestion ? (
            <Card size="small" title={`问题目标：${currentQuestion.question_goal}`}>
              <Paragraph>{currentQuestion.question_text}</Paragraph>
              <Tag>{currentQuestion.core_or_probe === 'core' ? '核心题' : '追问'}</Tag>
              <Input.TextArea
                rows={4}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="可以回答；也可以选择不知道 / 记不清 / 不愿回答"
                style={{ marginTop: 12 }}
              />
              <Space wrap style={{ marginTop: 12 }}>
                <Button type="primary" loading={busy} onClick={() => submitAnswer()}>提交回答</Button>
                <Button loading={busy} onClick={() => submitAnswer({ declined: true, reason: 'unknown' })}>不知道</Button>
                <Button loading={busy} onClick={() => submitAnswer({ declined: true, reason: 'forgot' })}>记不清</Button>
                <Button loading={busy} onClick={() => submitAnswer({ declined: true, reason: 'prefer_not_to_answer' })}>不愿回答</Button>
                <Button danger loading={busy} onClick={() => submitAnswer({ declined: true, reason: 'stop_followup' })}>停止追问</Button>
              </Space>
            </Card>
          ) : (
            <Alert type="success" showIcon message="当前没有更多问题，可确认观察结果或结束会话。" />
          )}
          <Card size="small" title="Observation 确认">
            {observations.length ? (
              <List
                dataSource={observations}
                renderItem={(item) => (
                  <List.Item
                    actions={item.candidate_confirmation_state === 'pending' ? [
                      <Button key="confirm" type="link" onClick={() => resolveObservation(item.id, 'confirm')}>确认</Button>,
                      <Button key="reject" type="link" danger onClick={() => resolveObservation(item.id, 'reject')}>拒绝</Button>,
                    ] : [<Tag key="state">{item.candidate_confirmation_state}</Tag>]}
                  >
                    <List.Item.Meta
                      title={<Space wrap><Tag>{item.observation_type}</Tag><span>{item.text}</span></Space>}
                      description={`原文偏移 ${item.source_start}-${item.source_end}${item.offset_valid === false ? '（偏移无效）' : ''}`}
                    />
                  </List.Item>
                )}
              />
            ) : <Text type="secondary">提交回答后会出现待确认观察结果</Text>}
          </Card>
          <Space>
            <Button onClick={() => exitSession('complete')}>完成会话</Button>
            <Button danger onClick={() => exitSession('revoke')}>撤回并停止使用</Button>
          </Space>
        </Space>
      )}
      <Divider />
      <Card size="small" title="面试记录">
        {history.length ? (
          <List
            size="small"
            dataSource={history}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button key="report" type="link" onClick={() => openHistory(item)}>
                    查看问答与反馈
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={MODES.find((modeItem) => modeItem.value === item.mode)?.label || item.mode}
                  description={`${item.status === 'completed' ? '已完成' : item.status === 'revoked' ? '已撤回' : '进行中'} · 回答 ${item.progress?.answered_count || 0}/${item.progress?.question_total || 0} · ${item.created_at ? new Date(item.created_at).toLocaleString() : ''}`}
                />
              </List.Item>
            )}
          />
        ) : <Text type="secondary">完成第一场结构化面试后，这里会保留问答记录和反馈。</Text>}
      </Card>
      {selectedReport && (
        <div style={{ marginTop: 12 }}>
          <InterviewFeedback report={selectedReport} />
        </div>
      )}
    </Card>
  );
}

import { useState, useRef, useEffect } from 'react';
import {
  Alert, Avatar, Button, Card, Checkbox, Input, List, message, Segmented,
  Select, Space, Typography,
} from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  PlayCircleOutlined,
  AudioOutlined,
  AudioMutedOutlined,
} from '@ant-design/icons';
import api, { getWsBaseUrl } from '../../api';
import {
  buildInterviewWsUrl,
  buildWebSocketAuthMessage,
  interviewControlMessageText,
  isWebSocketAuthOk,
  parseInterviewControlMessage,
} from '../../utils/interviewWebSocket';

const { Text } = Typography;

export default function Interview() {
  const [mode, setMode] = useState('profile');
  const [resumeId, setResumeId] = useState(null);
  const [resumes, setResumes] = useState([]);
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [connectionState, setConnectionState] = useState('idle');
  const [listening, setListening] = useState(false);
  const [pendingResult, setPendingResult] = useState(null);
  const [consents, setConsents] = useState({
    resume_write: false,
    job_recommendation: false,
    employer_share: false,
    model_improvement: false,
  });
  const [confirming, setConfirming] = useState(false);
  const ws = useRef(null);
  const authTimer = useRef(null);
  const closeNotice = useRef('');
  const chatEndRef = useRef(null);

  const userId = localStorage.getItem('user_id');

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (userId) {
      api.get(`/resumes/${userId}`).then((r) => setResumes(r.data || [])).catch(() => {});
      api.get('/interviews/results/mine', {
        params: { status: 'pending_confirmation' },
      }).then((response) => {
        const latest = response.data?.data?.[0];
        if (!latest) return;
        setPendingResult({
          id: latest.id,
          mode: latest.mode,
          status: latest.status,
          resumeId: latest.resume_id,
          applicationId: latest.application_id,
          extracted: latest.extracted || {},
        });
        setConsents(latest.requested_uses || {
          resume_write: false,
          job_recommendation: false,
          employer_share: false,
          model_improvement: false,
        });
        if (latest.resume_id) setResumeId(latest.resume_id);
      }).catch(() => {});
    }
  }, [userId]);

  const speakText = (text) => {
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel();
    const cleanText = text.replace(/\[INTERVIEW_END\]/g, '').replace(/\[CLAIM_DONE\]/g, '').trim();
    if (!cleanText) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    speechSynthesis.speak(utterance);
  };

  const buildWsUrl = () => {
    const applicationId = new URLSearchParams(window.location.search).get('applicationId');
    return buildInterviewWsUrl(getWsBaseUrl(), userId, {
      mode,
      resumeId,
      applicationId,
    });
  };

  const startInterview = () => {
    if (mode === 'claim_followup' && !resumeId) {
      message.warning('请先选择要追问的简历');
      return;
    }
    if (!localStorage.getItem('token')) {
      message.error('请先登录后再开始面试');
      return;
    }
    ws.current = new WebSocket(buildWsUrl());
    setConnectionState('connecting');
    closeNotice.current = '';
    ws.current.onopen = () => {
      setStarted(true);
      setConnectionState('authenticating');
      ws.current.send(
        buildWebSocketAuthMessage(localStorage.getItem('token'), consents),
      );
      authTimer.current = window.setTimeout(() => {
        if (!connected && ws.current?.readyState === WebSocket.OPEN) {
          closeNotice.current = '登录验证超时，请重新登录后再试';
          setConnectionState('auth_timeout');
          ws.current.close(1008, 'auth_timeout');
        }
      }, 10000);
      const dummy = new SpeechSynthesisUtterance('');
      dummy.volume = 0;
      speechSynthesis.speak(dummy);
    };
    ws.current.onmessage = (e) => {
      const msgText = e.data;
      if (isWebSocketAuthOk(msgText)) {
        window.clearTimeout(authTimer.current);
        setConnected(true);
        setConnectionState('authenticated');
        return;
      }
      const control = parseInterviewControlMessage(msgText);
      if (control?.type === 'error') {
        const notice = interviewControlMessageText(control);
        closeNotice.current = notice;
        setMessages((prev) => [...prev, { sender: 'bot', text: notice }]);
        if (
          control.error === 'subscription_inactive'
          || control.error === 'billing_account_missing'
        ) {
          setConnectionState('auth_failed');
        }
        return;
      }
      if (control?.type === 'interview_result') {
        setPendingResult(control);
        if (control.resumeId) setResumeId(control.resumeId);
        setMessages((prev) => [
          ...prev,
          { sender: 'bot', text: control.message },
        ]);
        return;
      }
      setMessages((prev) => [...prev, { sender: 'bot', text: msgText }]);
      speakText(msgText);
    };
    ws.current.onclose = (event) => {
      window.clearTimeout(authTimer.current);
      setConnected(false);
      setStarted(false);
      setConnectionState(
        event.code === 1008 && !closeNotice.current
          ? 'auth_failed'
          : 'disconnected',
      );
      if (closeNotice.current) {
        message.warning(closeNotice.current);
      } else if (event.code === 1008) {
        message.error('登录验证失败，请重新登录后再试');
      } else {
        message.info('面试已结束');
      }
    };
    ws.current.onerror = () => {
      window.clearTimeout(authTimer.current);
      message.error('连接失败，请重试');
      setStarted(false);
      setConnectionState('disconnected');
    };
  };

  const send = (text = input) => {
    if (!text.trim() || !ws.current || !connected) return;
    ws.current.send(text.trim());
    setMessages((prev) => [...prev, { sender: 'user', text: text.trim() }]);
    setInput('');
    if (window.speechSynthesis) speechSynthesis.cancel();
  };

  const recognitionRef = useRef(null);

  const startListening = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      message.error('当前浏览器不支持语音识别');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    recognition.lang = 'zh-CN';
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setInput(transcript);
      send(transcript);
    };
    recognition.onerror = (event) => {
      message.error(`语音识别错误: ${event.error}`);
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognition.start();
  };

  const stopListening = () => {
    try {
      recognitionRef.current?.stop?.();
    } catch {
      /* ignore */
    }
    setListening(false);
  };

  const setConsent = (key, checked) => {
    setConsents((current) => ({ ...current, [key]: checked }));
  };

  const confirmResult = async () => {
    if (!Object.values(consents).some(Boolean)) {
      message.warning('请至少选择一项用途；如不希望保留，请直接删除草稿');
      return;
    }
    if (consents.resume_write && !resumeId) {
      message.warning('写入简历前，请选择目标简历');
      return;
    }
    setConfirming(true);
    try {
      await api.post(`/interviews/results/${pendingResult.id}/confirm`, {
        allowed_uses: consents,
        resume_id: consents.resume_write ? resumeId : null,
      });
      message.success('已按你选择的用途确认');
      setPendingResult(null);
    } catch (error) {
      message.error(error.apiError?.message || '确认失败，请重试');
    } finally {
      setConfirming(false);
    }
  };

  const discardResult = async () => {
    setConfirming(true);
    try {
      await api.delete(`/interviews/results/${pendingResult.id}`);
      message.success('草稿及其中的面试数据已删除');
      setPendingResult(null);
    } catch (error) {
      message.error(error.apiError?.message || '删除失败，请重试');
    } finally {
      setConfirming(false);
    }
  };

  const modeDescriptions = {
    profile: '与 AI 面试官轻松对话；结果先保存为草稿，由你决定每一种用途',
    claim_followup: '补齐经历细节；未经确认，不会写入简历或分享给招聘方',
  };

  if (!started) {
    return (
      <Card className="content-card" title="AI 虚拟面试官">
        <div className="interview-start-panel" style={{ textAlign: 'center' }}>
          <RobotOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />

          {pendingResult && (
            <Card
              size="small"
              title="确认这次面试结果的用途"
              style={{ maxWidth: 560, margin: '0 auto 24px', textAlign: 'left' }}
            >
              <Alert
                showIcon
                type="warning"
                message="四项授权彼此独立，默认均未授权"
                description="确认前不会写入简历、影响职位推荐、分享给招聘方或用于模型改进。"
                style={{ marginBottom: 16 }}
              />
              <Space direction="vertical" style={{ width: '100%' }}>
                <Checkbox
                  checked={consents.resume_write}
                  onChange={(event) => setConsent('resume_write', event.target.checked)}
                >
                  将本次结果写入我选择的简历
                </Checkbox>
                {consents.resume_write && (
                  <Select
                    style={{ width: '100%' }}
                    placeholder="选择目标简历"
                    value={resumeId}
                    onChange={setResumeId}
                    options={resumes.map((resume) => ({
                      value: resume.id,
                      label: resume.parsed?.name
                        ? `${resume.parsed.name} 的简历`
                        : `简历 ${resume.id.slice(0, 8)}`,
                    }))}
                  />
                )}
                <Checkbox
                  checked={consents.job_recommendation}
                  onChange={(event) => setConsent('job_recommendation', event.target.checked)}
                >
                  允许用于我的职位推荐
                </Checkbox>
                <Checkbox
                  disabled={!pendingResult.applicationId}
                  checked={consents.employer_share}
                  onChange={(event) => setConsent('employer_share', event.target.checked)}
                >
                  分享给本次申请对应的招聘方
                </Checkbox>
                <Checkbox
                  checked={consents.model_improvement}
                  onChange={(event) => setConsent('model_improvement', event.target.checked)}
                >
                  允许用于模型质量改进
                </Checkbox>
              </Space>
              <Space style={{ marginTop: 20 }}>
                <Button
                  type="primary"
                  loading={confirming}
                  onClick={confirmResult}
                >
                  按以上选择确认
                </Button>
                <Button
                  danger
                  loading={confirming}
                  onClick={discardResult}
                >
                  删除草稿
                </Button>
              </Space>
            </Card>
          )}

          <div style={{ maxWidth: 480, margin: '0 auto 20px' }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>面试模式</Text>
            <Segmented
              value={mode}
              onChange={setMode}
              block
              options={[
                { label: '普通面试', value: 'profile' },
                { label: '简历追问', value: 'claim_followup' },
              ]}
            />
          </div>

          {mode === 'claim_followup' && (
            <div style={{ maxWidth: 480, margin: '0 auto 20px' }}>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12, textAlign: 'left' }}
                message="简历 claim 追问"
                description="为了让这段经历表达得更可信，AI 面试官会帮你补齐细节。不会检测你是否造假。"
              />
              <Select
                style={{ width: '100%' }}
                placeholder="选择要追问的简历"
                value={resumeId}
                onChange={setResumeId}
                options={resumes.map((r) => ({
                  value: r.id,
                  label: r.parsed?.name ? `${r.parsed.name} 的简历` : `简历 ${r.id.slice(0, 8)}`,
                }))}
              />
            </div>
          )}

          {!pendingResult && (
            <Card
              size="small"
              title="本次面试的用途偏好"
              style={{ maxWidth: 560, margin: '0 auto 20px', textAlign: 'left' }}
            >
              <Alert
                showIcon
                type="info"
                message="四项用途独立选择，结束后还会请你再次确认"
                description="不开启的用途不会使用本次面试原文或结构化结果。"
                style={{ marginBottom: 12 }}
              />
              <Space direction="vertical">
                <Checkbox
                  checked={consents.resume_write}
                  onChange={(event) => setConsent('resume_write', event.target.checked)}
                >
                  帮助生成或改写我的简历
                </Checkbox>
                <Checkbox
                  checked={consents.job_recommendation}
                  onChange={(event) => setConsent('job_recommendation', event.target.checked)}
                >
                  将面试草稿作为个人岗位推荐的额外信号
                </Checkbox>
                <Checkbox
                  disabled={!new URLSearchParams(window.location.search).get('applicationId')}
                  checked={consents.employer_share}
                  onChange={(event) => setConsent('employer_share', event.target.checked)}
                >
                  与本次申请对应的招聘方分享指定结果
                </Checkbox>
                <Checkbox
                  checked={consents.model_improvement}
                  onChange={(event) => setConsent('model_improvement', event.target.checked)}
                >
                  去标识化后用于模型质量改进
                </Checkbox>
              </Space>
            </Card>
          )}

          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={startInterview}
          >
            {mode === 'claim_followup' ? '开始简历追问' : '开始面试'}
          </Button>
          <p style={{ marginTop: 16, color: '#64748b' }}>
            {modeDescriptions[mode]}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="content-card"
      title={mode === 'claim_followup' ? 'AI 简历追问' : 'AI 虚拟面试官'}
      extra={(
        <Text type={connected ? 'success' : 'secondary'}>
          {connected ? '● 已连接' : '未连接'}
          {!connected && connectionState === 'authenticating' ? '（验证登录中）' : ''}
        </Text>
      )}
    >
      {mode === 'claim_followup' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="简历 claim 追问模式"
          description="逐条补齐经历细节；完成后由你确认是否写入简历或分享。"
        />
      )}

      <div className="interview-chat">
        <List
          dataSource={messages}
          renderItem={(item, idx) => (
            <List.Item
              key={idx}
              style={{
                justifyContent: item.sender === 'user' ? 'flex-end' : 'flex-start',
                border: 'none',
              }}
            >
              <List.Item.Meta
                avatar={
                  item.sender === 'user' ? (
                    <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#87d068' }} />
                  ) : (
                    <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#1890ff' }} />
                  )
                }
                description={(
                  <div
                    className={
                      item.sender === 'user'
                        ? 'interview-bubble interview-bubble-user'
                        : 'interview-bubble interview-bubble-bot'
                    }
                  >
                    {item.text}
                  </div>
                )}
              />
            </List.Item>
          )}
        />
        <div ref={chatEndRef} />
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Button
          icon={listening ? <AudioMutedOutlined /> : <AudioOutlined />}
          onClick={listening ? stopListening : startListening}
          type={listening ? 'primary' : 'default'}
          danger={listening}
        >
          {listening ? '聆听中...' : '语音'}
        </Button>
        <Input.Search
          enterButton="发送"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onSearch={() => send()}
          placeholder="输入你的回答..."
          disabled={!connected}
        />
      </Space.Compact>
    </Card>
  );
}

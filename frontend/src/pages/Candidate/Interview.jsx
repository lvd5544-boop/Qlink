import { useState, useRef, useEffect } from 'react';
import { Card, Button, Input, List, Avatar, message, Typography, Space } from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  PlayCircleOutlined,
  AudioOutlined,
  AudioMutedOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

export default function Interview() {
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [listening, setListening] = useState(false);
  const ws = useRef(null);
  const chatEndRef = useRef(null);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 语音朗读函数
  const speakText = (text) => {
    if (!window.speechSynthesis) return;
    // 先停掉当前语音，避免重叠
    speechSynthesis.cancel();
    const cleanText = text.replace(/\[INTERVIEW_END\]/g, '').trim();
    if (!cleanText) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.onerror = (e) => console.warn('语音播放错误:', e.error);
    speechSynthesis.speak(utterance);
  };

  // 开始面试：建立 WebSocket 连接
  const startInterview = () => {
    const userId = localStorage.getItem('user_id');
    ws.current = new WebSocket(`ws://localhost:8000/ws/interview/${userId}`);
    ws.current.onopen = () => {
      setConnected(true);
      setStarted(true);
      // 激活音频上下文（解决浏览器自动播放限制）
      const dummy = new SpeechSynthesisUtterance('');
      dummy.volume = 0;
      speechSynthesis.speak(dummy);
    };
    ws.current.onmessage = (e) => {
      const msgText = e.data;
      setMessages((prev) => [...prev, { sender: 'bot', text: msgText }]);
      speakText(msgText); // 朗读面试官的回复
    };
    ws.current.onclose = () => {
      setConnected(false);
      setStarted(false);
      message.info('面试已结束');
    };
    ws.current.onerror = () => {
      message.error('连接失败，请重试');
      setStarted(false);
    };
  };

  // 发送消息
  const send = (text = input) => {
    if (!text.trim() || !ws.current) return;
    ws.current.send(text.trim());
    setMessages((prev) => [...prev, { sender: 'user', text: text.trim() }]);
    setInput('');
    // 用户说话时停止朗读
    if (window.speechSynthesis) speechSynthesis.cancel();
  };

  // 语音识别
  const startListening = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      message.error('当前浏览器不支持语音识别');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setInput(transcript);
      send(transcript); // 自动发送识别结果
    };
    recognition.onerror = (event) => {
      message.error(`语音识别错误: ${event.error}`);
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognition.start();
  };

  const stopListening = () => {
    if (window.recognition) {
      window.recognition.stop();
    }
    setListening(false);
  };

  // 还未开始面试时，显示开始按钮
  if (!started) {
    return (
      <Card className="content-card" title="AI 虚拟面试官">
        <div className="interview-start-panel">
          <RobotOutlined />
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={startInterview}
          >
            开始面试
          </Button>
          <p style={{ marginTop: 16, color: '#64748b' }}>
            与 AI 面试官进行文字或语音对话，自动完善您的求职画像
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="content-card"
      title="AI 虚拟面试官"
      extra={
        <Text type={connected ? 'success' : 'secondary'}>
          {connected ? '● 已连接' : '未连接'}
        </Text>
      }
    >
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
                description={
                  <div
                    className={
                      item.sender === 'user'
                        ? 'interview-bubble interview-bubble-user'
                        : 'interview-bubble interview-bubble-bot'
                    }
                  >
                    {item.text}
                  </div>
                }
              />
            </List.Item>
          )}
        />
        <div ref={chatEndRef} />
      </div>

      {/* 输入区域（含语音按钮） */}
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
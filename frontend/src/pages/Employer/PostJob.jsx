import { useState } from 'react';
import { Card, Upload, Button, Input, message, Descriptions, Tag, Space } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import api from '../../api';

export default function PostJob() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [textInput, setTextInput] = useState('');
  const employerId = localStorage.getItem('user_id');

  const handleUpload = (file) => {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    api.post(`/post-job?employer_id=${employerId}`, formData)
      .then((res) => {
        setResult(res.data);
        message.success('岗位发布成功');
      })
      .catch(() => message.error('发布失败'))
      .finally(() => setLoading(false));
    return false;
  };

  const handleTextSubmit = () => {
    if (!textInput.trim()) return;
    setLoading(true);
    api.post(`/post-job?employer_id=${employerId}`, null, {
      params: { description_text: textInput }
    })
      .then((res) => {
        setResult(res.data);
        message.success('岗位发布成功');
      })
      .catch(() => message.error('发布失败'))
      .finally(() => setLoading(false));
  };

  return (
    <Card className="content-card" title="发布新岗位">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Upload beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.txt">
          <Button icon={<UploadOutlined />} loading={loading}>上传 JD 文件</Button>
        </Upload>
        <div>或直接填写描述：</div>
        <Input.TextArea rows={6} value={textInput} onChange={(e) => setTextInput(e.target.value)} placeholder="粘贴岗位描述..." />
        <Button type="primary" onClick={handleTextSubmit} loading={loading}>提交文本</Button>
      </Space>

      {result && (
        <Descriptions bordered style={{ marginTop: 24 }}>
          <Descriptions.Item label="岗位名称">{result.title}</Descriptions.Item>
          <Descriptions.Item label="地点">{result.location || '未指定'}</Descriptions.Item>
          <Descriptions.Item label="薪资范围">{result.salary_range || '面议'}</Descriptions.Item>
          <Descriptions.Item label="技能要求" span={2}>
            <Space wrap>
              {result.required_skills?.map((s, idx) => (
                <Tag color="green" key={idx}>{s.name}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="职责" span={2}>
            <ul>
              {result.responsibilities?.map((r, idx) => <li key={idx}>{r}</li>)}
            </ul>
          </Descriptions.Item>
          <Descriptions.Item label="经验要求">{result.experience_years ? `${result.experience_years} 年` : '不限'}</Descriptions.Item>
          <Descriptions.Item label="学历">{result.education || '不限'}</Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}
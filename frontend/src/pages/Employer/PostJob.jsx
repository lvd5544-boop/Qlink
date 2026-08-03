import { useState } from 'react';
import { Alert, Button, Card, Input, message, Space, Upload } from 'antd';
import { CheckCircleOutlined, UploadOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import JobProfileEditor from '../../components/JobProfileEditor';
import { confirmationPayload } from '../../components/jobProfileEditorUtils';

export default function PostJob() {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [textInput, setTextInput] = useState('');

  const parseAndCreate = async (request) => {
    setLoading(true);
    try {
      const res = await request();
      setResult(res.data);
      message.success('岗位草稿已生成，请确认筛选重点后发布');
    } catch (err) {
      message.error(`发布失败：${getApiErrorMessage(err, '请检查 JD 后重试')}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    parseAndCreate(() => api.post('/post-job', formData));
    return false;
  };

  const handleTextSubmit = () => {
    if (!textInput.trim()) {
      message.warning('请先粘贴岗位描述');
      return;
    }
    parseAndCreate(() => api.post('/post-job', null, {
      params: { description_text: textInput },
    }));
  };

  const handleSave = async (parsed, requirementChoices) => {
    if (!result?.job_id) return;
    setSaving(true);
    try {
      await api.put(`/jobs/${result.job_id}`, {
        parsed_json: { ...parsed, _publication_status: 'draft' },
      });
      const profile = await api.get(`/advisor/jobs/${result.job_id}/profile`);
      const requirements = confirmationPayload(profile.data, requirementChoices);
      await api.post(
        `/advisor/jobs/${result.job_id}/profile/confirm`,
        { requirements },
        {
          headers: {
            'Idempotency-Key': `publish-job-${result.job_id}-${Date.now()}`,
          },
        },
      );
      message.success('岗位已发布，筛选重点已同步到海选工作台');
      navigate(`/employer/screening?job_id=${result.job_id}`);
    } catch (err) {
      message.error(`保存失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      className="content-card"
      title="发布新岗位"
      extra={<Link to="/employer/my-jobs"><Button>我的岗位</Button></Link>}
    >
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="粘贴 JD，确认岗位和筛选重点，一次完成发布。"
          description="系统先生成草稿，不会在你确认前向求职者公开。"
        />
        <Upload beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.txt">
          <Button icon={<UploadOutlined />} loading={loading}>上传 JD 文件</Button>
        </Upload>
        <div>或直接填写描述：</div>
        <Input.TextArea
          rows={7}
          value={textInput}
          onChange={(event) => setTextInput(event.target.value)}
          placeholder="粘贴岗位描述..."
        />
        <Button type="primary" onClick={handleTextSubmit} loading={loading}>提取岗位信息</Button>
      </Space>

      {result && (
        <>
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            message="岗位草稿已生成"
            description="在下面检查内容并设置筛选重点，点击一次即可正式发布。"
            style={{ marginTop: 20 }}
          />
          <JobProfileEditor
            key={result.job_id}
            initialValue={{ ...result, _publication_status: 'draft' }}
            saving={saving}
            onSave={handleSave}
          />
        </>
      )}
    </Card>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert, Button, Card, message, Spin } from 'antd';
import api from '../../api';
import { getApiErrorMessage } from '../../utils/apiError';
import JobProfileEditor from '../../components/JobProfileEditor';
import {
  confirmationPayload,
  decisionsFromProfile,
} from '../../components/jobProfileEditorUtils';

export default function EditJob() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [job, setJob] = useState(null);
  const [requirementDecisions, setRequirementDecisions] = useState([]);

  useEffect(() => {
    api.get('/jobs/mine')
      .then(async (res) => {
        const found = (res.data || []).find((item) => item.id === jobId);
        if (!found) {
          message.error('未找到该岗位');
          return;
        }
        setJob(found);
        const profile = await api.get(`/advisor/jobs/${jobId}/profile`);
        setRequirementDecisions(decisionsFromProfile(profile.data));
      })
      .catch((err) => message.error(`加载岗位详情失败：${getApiErrorMessage(err, '请重试')}`))
      .finally(() => setLoading(false));
  }, [jobId]);

  const handleSave = async (parsed, choices) => {
    setSaving(true);
    try {
      await api.put(`/jobs/${jobId}`, { parsed_json: parsed });
      const profile = await api.get(`/advisor/jobs/${jobId}/profile`);
      await api.post(
        `/advisor/jobs/${jobId}/profile/confirm`,
        { requirements: confirmationPayload(profile.data, choices) },
        { headers: { 'Idempotency-Key': `confirm-job-profile-${jobId}-${Date.now()}` } },
      );
      message.success('岗位已更新，筛选重点已同步');
      navigate('/employer/my-jobs');
    } catch (err) {
      message.error(`保存失败：${getApiErrorMessage(err, '请重试')}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spin />;

  return (
    <Card
      className="content-card"
      title="编辑岗位"
      extra={<Button onClick={() => navigate('/employer/my-jobs')}>返回</Button>}
    >
      <Alert
        type="info"
        showIcon
        message="JD 原文保留不变；这里修改的是招聘方确认后的结构化岗位信息。"
      />
      {job?.parsed && (
        <JobProfileEditor
          initialValue={job.parsed}
          saving={saving}
          onSave={handleSave}
          initialRequirementDecisions={requirementDecisions}
          submitText="保存岗位与筛选重点"
        />
      )}
    </Card>
  );
}

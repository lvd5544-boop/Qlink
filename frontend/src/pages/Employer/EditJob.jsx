import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Form, Input, Button, message, Spin } from 'antd';
import api from '../../api';

export default function EditJob() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [form] = Form.useForm();

  useEffect(() => {
    api.get('/jobs/mine')
      .then(res => {
        const job = res.data.find(j => j.id === jobId);
        if (job && job.parsed) {
          form.setFieldsValue({
            title: job.parsed.title || '',
            location: job.parsed.location || '',
            salary_range: job.parsed.salary_range || '',
            required_skills: (job.parsed.required_skills || []).map(s => s.name).join(', '),
            experience_years: job.parsed.experience_years || '',
            education: job.parsed.education || '',
            responsibilities: (job.parsed.responsibilities || []).join('\n'),
          });
        }
      })
      .catch(() => message.error('加载岗位详情失败'))
      .finally(() => setLoading(false));
  }, [form, jobId]);

  const handleSave = async (values) => {
    const parsed = {
      title: values.title,
      location: values.location,
      salary_range: values.salary_range,
      required_skills: values.required_skills.split(',').map(s => ({ name: s.trim(), level: 'intermediate' })),
      experience_years: values.experience_years ? parseInt(values.experience_years) : null,
      education: values.education,
      responsibilities: values.responsibilities.split('\n').filter(l => l.trim()),
    };
    try {
      await api.put(`/jobs/${jobId}`, { parsed_json: parsed });
      message.success('保存成功');
      navigate('/employer/my-jobs');
    } catch {
      message.error('保存失败');
    }
  };

  if (loading) return <Spin />;

  return (
    <Card className="content-card" title="编辑岗位" extra={<Button onClick={() => navigate('/employer/my-jobs')}>返回</Button>}>
      <Form form={form} layout="vertical" onFinish={handleSave}>
        <Form.Item name="title" label="岗位名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="location" label="工作地点">
          <Input />
        </Form.Item>
        <Form.Item name="salary_range" label="薪资范围">
          <Input placeholder="如 20k-30k" />
        </Form.Item>
        <Form.Item name="required_skills" label="技能要求（逗号分隔）">
          <Input placeholder="Spring Boot, Kafka, ..." />
        </Form.Item>
        <Form.Item name="experience_years" label="经验年限">
          <Input type="number" />
        </Form.Item>
        <Form.Item name="education" label="学历要求">
          <Input placeholder="本科及以上" />
        </Form.Item>
        <Form.Item name="responsibilities" label="岗位职责（每行一条）">
          <Input.TextArea rows={4} />
        </Form.Item>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form>
    </Card>
  );
}

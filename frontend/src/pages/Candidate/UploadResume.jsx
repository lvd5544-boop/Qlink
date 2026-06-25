import { useState } from 'react';
import { Upload, Button, Card, message, Descriptions, Tag, Space } from 'antd';
import { UploadOutlined, FileTextOutlined } from '@ant-design/icons';
import api from '../../api';
import ResumeHealthPanel from '../../components/ResumeHealthPanel';
import { notifyDashboardRefresh } from '../../utils/dashboardSync';

export default function UploadResume() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const uploadProps = {
    beforeUpload: (file) => {
      setLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      api.post('/parse-resume', formData)
        .then((res) => {
          setResult(res.data);
          notifyDashboardRefresh({
            indicators: {
              health_score: res.data.health_check?.overall_score,
              completeness_score: res.data.health_check?.completeness?.score,
              quantification_score: res.data.health_check?.quantification?.score,
            },
          });
          message.success('简历解析成功，体检与匹配正在后台计算');
        })
        .catch(() => message.error('解析失败'))
        .finally(() => setLoading(false));
      return false; // 阻止默认上传行为
    },
    showUploadList: false,
  };

  return (
    <Card className="content-card" title="上传简历" extra={<Button icon={<FileTextOutlined />} onClick={() => setResult(null)}>清空</Button>}>
      <Upload {...uploadProps} accept=".pdf,.docx,.txt">
        <div className="upload-dragger-area">
          <Button icon={<UploadOutlined />} loading={loading} type="primary" size="large">
            选择文件并上传
          </Button>
          <p style={{ margin: '12px 0 0', color: '#64748b', fontSize: 13 }}>
            支持 PDF、Word、TXT，上传后 AI 自动解析
          </p>
        </div>
      </Upload>

      {result?.health_check && (
        <Card size="small" style={{ marginTop: 24 }} title="简历体检">
          <ResumeHealthPanel healthCheck={result.health_check} />
        </Card>
      )}

      {result && (
        <Descriptions bordered column={2} style={{ marginTop: 24 }}>
          <Descriptions.Item label="姓名">{result.name || '未识别'}</Descriptions.Item>
          <Descriptions.Item label="期望职位">{result.expected_job_title || '无'}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{result.email || '无'}</Descriptions.Item>
          <Descriptions.Item label="电话">{result.phone || '无'}</Descriptions.Item>
          <Descriptions.Item label="技能" span={2}>
            <Space wrap>
              {result.skills?.map((s, idx) => (
                <Tag color="blue" key={idx}>{s.name}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="工作经历" span={2}>
            {result.work_experience?.map((exp, idx) => (
              <div key={idx}>
                <strong>{exp.company}</strong> - {exp.position} ({exp.duration_years}年)
                <br />
                {exp.description}
              </div>
            ))}
          </Descriptions.Item>
          <Descriptions.Item label="学历">{result.education || '无'}</Descriptions.Item>
          <Descriptions.Item label="兴趣爱好">
            {result.hobbies?.join(', ') || '无'}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
}
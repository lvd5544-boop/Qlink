import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, Button, Card, Col, message, Row, Typography } from 'antd';
import { UploadOutlined, FileTextOutlined, ArrowRightOutlined } from '@ant-design/icons';
import api from '../../api';
import ResumeHealthPanel from '../../components/ResumeHealthPanel';
import ResumeEditForm from '../../components/ResumeEditForm';
import ResumeDocumentView from '../../components/ResumeDocumentView';
import { notifyDashboardRefresh } from '../../utils/dashboardSync';
import { getApiErrorMessage } from '../../utils/apiError';

export default function UploadResume() {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [editData, setEditData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [applyingId, setApplyingId] = useState(null);

  const parsedOnly = (value) => {
    const copy = { ...(value || {}) };
    delete copy.resume_id;
    delete copy.health_check;
    delete copy.match_job_id;
    return copy;
  };

  const uploadProps = {
    beforeUpload: (file) => {
      setLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      api.post('/parse-resume', formData)
        .then((res) => {
          setResult(res.data);
          setEditData(parsedOnly(res.data));
          notifyDashboardRefresh({
            indicators: {
              health_score: res.data.health_check?.overall_score,
              completeness_score: res.data.health_check?.completeness?.score,
              quantification_score: res.data.health_check?.quantification?.score,
            },
          });
          message.success('简历解析成功，体检与匹配正在后台计算');
        })
        .catch((error) => {
          message.error(getApiErrorMessage(error, '简历解析失败，请稍后重试'));
        })
        .finally(() => setLoading(false));
      return false; // 阻止默认上传行为
    },
    showUploadList: false,
  };

  const saveEdits = async () => {
    if (!result?.resume_id || !editData) return;
    setSaving(true);
    try {
      const response = await api.put(`/resumes/${result.resume_id}`, { parsed_json: editData });
      setResult((current) => ({ ...current, ...editData, health_check: response.data.health_check }));
      message.success('修改已保存，诊断和岗位匹配已重新计算');
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存修改失败'));
    } finally {
      setSaving(false);
    }
  };

  const applySuggestion = async (suggestion) => {
    setApplyingId(suggestion.id);
    try {
      const response = await api.post(`/resumes/${result.resume_id}/apply-suggestion`, {
        patch: suggestion.patch,
        suggestion_id: suggestion.db_id,
        suggestion_key: suggestion.id,
        job_id: suggestion.job_id,
      });
      setEditData(response.data.parsed_json);
      setResult((current) => ({
        ...current,
        ...response.data.parsed_json,
        health_check: response.data.health_check,
      }));
      message.success('建议已采纳，并同步到右侧预览');
    } catch (error) {
      message.error(getApiErrorMessage(error, '采纳失败'));
    } finally {
      setApplyingId(null);
    }
  };

  const dismissSuggestion = async (suggestion) => {
    try {
      const response = await api.post(`/resumes/${result.resume_id}/dismiss-suggestion`, {
        suggestion_id: suggestion.db_id,
        suggestion_key: suggestion.id,
      });
      setResult((current) => ({
        ...current,
        health_check: {
          ...current.health_check,
          actionable_suggestions: response.data?.pending_suggestions || [],
        },
      }));
    } catch (error) {
      message.error(getApiErrorMessage(error, '忽略建议失败'));
    }
  };

  return (
    <Card className="content-card" title="上传简历" extra={<Button icon={<FileTextOutlined />} onClick={() => { setResult(null); setEditData(null); }}>清空</Button>}>
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

      {result && editData && (
        <div style={{ marginTop: 24 }}>
          <Typography.Title level={4}>解析完成：现在就能修改、预览和采纳</Typography.Title>
          <Typography.Paragraph type="secondary">
            左侧字段可直接编辑；中间实时预览；右侧每条建议都可先改写再采纳，不再是只读报告。
          </Typography.Paragraph>
          <Row gutter={[16, 16]} align="stretch">
            <Col xs={24} xl={7}>
              <Card size="small" title="① 修正提取结果" styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}>
                <ResumeEditForm data={editData} onChange={setEditData} onSave={saveEdits} saving={saving} />
              </Card>
            </Col>
            <Col xs={24} xl={8}>
              <Card size="small" title="② 实时简历预览" styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}>
                <ResumeDocumentView parsed={editData} />
              </Card>
            </Col>
            <Col xs={24} xl={9}>
              <Card size="small" title="③ 诊断、改写与采纳" styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}>
                <ResumeHealthPanel
                  healthCheck={result.health_check}
                  resumeId={result.resume_id}
                  onApplySuggestion={applySuggestion}
                  onDismissSuggestion={dismissSuggestion}
                  applyingId={applyingId}
                />
                <Button
                  block
                  type="primary"
                  icon={<ArrowRightOutlined />}
                  style={{ marginTop: 16 }}
                  onClick={() => navigate(`/candidate/resumes?resumeId=${result.resume_id}`)}
                >
                  继续做岗位匹配与深度优化
                </Button>
              </Card>
            </Col>
          </Row>
        </div>
      )}
    </Card>
  );
}

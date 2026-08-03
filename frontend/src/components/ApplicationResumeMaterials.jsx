import { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Empty, Segmented, Spin, Tabs, Typography, message } from 'antd';
import api from '../api';
import { getApiErrorMessage } from '../utils/apiError';
import ResumeDocumentView from './ResumeDocumentView';

const { Paragraph, Text } = Typography;

export default function ApplicationResumeMaterials({ applicationId }) {
  const [loading, setLoading] = useState(true);
  const [materials, setMaterials] = useState(null);
  const [versionId, setVersionId] = useState('');

  useEffect(() => {
    let cancelled = false;
    api.get(`/applications/${applicationId}/materials`)
      .then((res) => {
        if (cancelled) return;
        setMaterials(res.data);
        setVersionId(res.data?.current_resume_version_id || res.data?.versions?.[0]?.version_id || '');
      })
      .catch((err) => {
        if (!cancelled) message.error(`加载投递材料失败：${getApiErrorMessage(err, '请重试')}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [applicationId]);

  const versions = useMemo(() => materials?.versions || [], [materials]);
  const selected = useMemo(
    () => versions.find((item) => item.version_id === versionId)
      || materials?.current_submission
      || materials?.initial_submission,
    [materials, versionId, versions],
  );

  if (loading) return <Spin />;
  if (!selected?.parsed_json && !selected?.raw_text) return <Empty description="该申请暂无可查看的投递材料" />;

  return (
    <Card type="inner" title="本次申请授权的简历材料">
      <Alert
        type="info"
        showIcon
        message={materials?.disclaimer}
        style={{ marginBottom: 12 }}
      />
      {versions.length > 1 && (
        <Segmented
          block
          value={versionId}
          onChange={setVersionId}
          options={versions.map((item, index) => ({
            value: item.version_id,
            label: index === 0 ? '最初投递版本' : `更换版本 ${index + 1}`,
          }))}
          style={{ marginBottom: 12 }}
        />
      )}
      <Tabs
        items={[
          {
            key: 'structured',
            label: '投递版本（含已采纳改写）',
            children: <ResumeDocumentView parsed={selected.parsed_json} />,
          },
          {
            key: 'original',
            label: '上传原文',
            children: selected.raw_text ? (
              <Paragraph
                copyable
                style={{ whiteSpace: 'pre-wrap', maxHeight: 560, overflow: 'auto' }}
              >
                {selected.raw_text}
              </Paragraph>
            ) : <Text type="secondary">历史申请未保存原文，只能查看投递时的结构化快照。</Text>,
          },
        ]}
      />
    </Card>
  );
}

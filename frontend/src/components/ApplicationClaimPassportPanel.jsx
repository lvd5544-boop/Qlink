import { useEffect, useState } from 'react';
import { Alert, Card, Empty, List, Space, Spin, Tag, Typography } from 'antd';
import api from '../api';

const { Text } = Typography;

const stateLabel = {
  supported_by_user_evidence: ['有用户证据支持', 'green'],
  not_enough_information: ['信息不足', 'orange'],
  conflict_detected: ['存在冲突', 'red'],
};

export default function ApplicationClaimPassportPanel({ applicationId }) {
  const [state, setState] = useState({ loading: false, claims: [] });

  useEffect(() => {
    if (!applicationId) return undefined;
    let active = true;
    const timer = setTimeout(async () => {
      if (active) setState((previous) => ({ ...previous, loading: true }));
      try {
        const response = await api.get(`/applications/${applicationId}/claim-passport`);
        if (active) setState({ loading: false, claims: response.data?.claims || [] });
      } catch {
        if (active) setState({ loading: false, claims: [] });
      }
    }, 0);
    return () => { active = false; clearTimeout(timer); };
  }, [applicationId]);

  return (
    <Card size="small" title="履历主张快照" style={{ marginTop: 12 }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 8 }}
        message="仅显示本次投递快照"
        description="“有用户证据支持”不等于事实认证；招聘方看不到候选人之后新增的私密补充内容。"
      />
      <Spin spinning={state.loading}>
        {state.claims.length ? (
          <List
            size="small"
            dataSource={state.claims}
            renderItem={(item) => {
              const label = stateLabel[item.evidence_state] || ['信息不足', 'default'];
              return (
                <List.Item>
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Space wrap><Tag color={label[1]}>{label[0]}</Tag><Tag>{item.claim_type}</Tag></Space>
                    <Text>{item.text_snapshot}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.field_path}</Text>
                  </Space>
                </List.Item>
              );
            }}
          />
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该历史申请尚未生成 Claim Passport 快照" />}
      </Spin>
    </Card>
  );
}

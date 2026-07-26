import { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Col, Progress, Row, Skeleton, Space, Tag, Typography } from 'antd';
import api from '../api';

const { Text } = Typography;

const FEATURE_LABELS = {
  resume_coach: 'Resume Coach',
  evidence_regenerate: '忠实重写',
  credibility_audit: '简历审计',
  interview_session: '免费面试（日）',
  interview_turn: '单次面试轮数',
};

function formatCny(minorUnits) {
  return `¥${(Number(minorUnits || 0) / 100).toFixed(0)}`;
}

function Entitlement({ item }) {
  const hasUsage = item.used != null && item.limit != null;
  const percent = hasUsage && item.limit > 0
    ? Math.min(100, Math.round(((item.used + (item.reserved || 0)) / item.limit) * 100))
    : 0;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Text>{FEATURE_LABELS[item.feature] || item.feature}</Text>
        <Text strong>
          {hasUsage
            ? `${item.remaining}/${item.limit}`
            : `${item.limit ?? '不限'} / ${item.period === 'session' ? 'session' : item.period}`}
        </Text>
      </div>
      {hasUsage && <Progress percent={percent} showInfo={false} size="small" />}
    </div>
  );
}

export default function BillingSummaryCard({ audience }) {
  const [billing, setBilling] = useState(null);
  const [failed, setFailed] = useState(false);
  const endpoint = audience === 'organization'
    ? '/billing/organization'
    : '/billing/me';

  useEffect(() => {
    let active = true;
    api.get(endpoint)
      .then((response) => {
        if (active) setBilling(response.data);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [endpoint]);

  const proPlan = useMemo(
    () => billing?.available_plans?.find((plan) => plan.code === 'candidate-pro-v1'),
    [billing],
  );

  if (failed) {
    return (
      <Alert
        type="warning"
        showIcon
        message="暂时无法读取 AI 权益"
        description="不会因此显示或泄露模型 token 与供应商成本。"
      />
    );
  }
  if (!billing) return <Card><Skeleton active paragraph={{ rows: 2 }} /></Card>;

  return (
    <Card
      title={audience === 'organization' ? '企业席位与共享额度' : 'AI 功能权益'}
      extra={<Tag color="blue">{billing.plan.name}</Tag>}
      style={{ marginBottom: 24 }}
    >
      <Row gutter={[24, 16]}>
        <Col xs={24} md={audience === 'organization' ? 16 : 14}>
          {(billing.entitlements || []).map((item) => (
            <Entitlement
              key={`${item.feature}:${item.period}`}
              item={item}
            />
          ))}
        </Col>
        <Col xs={24} md={audience === 'organization' ? 8 : 10}>
          {audience === 'organization' ? (
            <Space direction="vertical">
              <Text>
                席位：{billing.seats.occupied}/{billing.seats.quantity}
              </Text>
              <Text>
                单席位：{formatCny(billing.plan.price_minor_units)}/月
              </Text>
              {billing.available_credit_packs?.map((pack) => (
                <Tag key={pack.code} color="gold">
                  加购 {pack.grant_units} credits：{formatCny(pack.price_minor_units)}
                </Tag>
              ))}
            </Space>
          ) : (
            <Space direction="vertical">
              <Text>当前：{formatCny(billing.plan.price_minor_units)}/月</Text>
              {proPlan && (
                <Tag color="purple">
                  Candidate Pro：{formatCny(proPlan.price_minor_units)}/月
                </Tag>
              )}
              <Text type="secondary">
                AI 面试免费，受每日 session 与单次轮数公平使用限制。
              </Text>
            </Space>
          )}
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            月度额度按 {billing.reset_timezone} 重置；实际 token 成本仅管理员可见。
          </Text>
        </Col>
      </Row>
    </Card>
  );
}

import { Alert } from 'antd';
import { useEffect, useState } from 'react';
import api from '../api';

/**
 * Shows when /ready reports rules_only / AI disabled.
 * Rules, editing, search and apply remain available.
 */
export default function AiAvailabilityBanner({ style }) {
  const [modelState, setModelState] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/ready')
      .then((res) => {
        if (cancelled) return;
        setModelState(res.data?.checks?.model || null);
      })
      .catch(() => {
        if (!cancelled) setModelState(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (modelState?.mode !== 'rules_only') return null;
  const reason = modelState.reason === 'ai_disabled'
    ? '你已关闭 AI。'
    : ['configuration_missing', 'api_key_missing'].includes(modelState.reason)
      ? '尚未完成模型配置。'
      : '模型供应商当前不可用。';

  return (
    <Alert
      className="editorial-guidance-card editorial-guidance-card-compact"
      type="info"
      showIcon
      style={style}
      message="AI 生成暂时不可用"
      description={`${reason} 你仍然可以查找岗位、编辑简历和管理申请；需要生成改写或智能追问时再完成模型配置。`}
    />
  );
}

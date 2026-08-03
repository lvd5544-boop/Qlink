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
    : modelState.reason === 'api_key_missing'
      ? '尚未配置模型 API Key。'
      : '模型供应商当前不可用。';

  return (
    <Alert
      type="info"
      showIcon
      style={style}
      message="当前处于规则模式"
      description={`${reason} 精准定位、人工编辑、规则诊断、Evidence Vault、岗位检索和投递仍可使用；需要生成式改写或 AI 追问时，请先完成模型配置。`}
    />
  );
}

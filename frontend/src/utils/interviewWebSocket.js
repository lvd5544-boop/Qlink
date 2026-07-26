export function buildInterviewWsUrl(
  baseUrl,
  userId,
  {
    mode = 'profile',
    resumeId = null,
    applicationId = null,
  } = {},
) {
  const params = new URLSearchParams({ mode });
  if (mode === 'claim_followup' && resumeId) {
    params.set('resume_id', resumeId);
  }
  if (applicationId) {
    params.set('application_id', applicationId);
  }
  return `${baseUrl}/ws/interview/${userId}?${params.toString()}`;
}

export function isWebSocketAuthOk(message) {
  try {
    return JSON.parse(message)?.type === 'auth_ok';
  } catch {
    return false;
  }
}

export function parseInterviewControlMessage(message) {
  try {
    const payload = JSON.parse(message);
    if (!payload || typeof payload !== 'object') return null;
    if (payload.type === 'auth_ok') {
      return { type: 'auth_ok' };
    }
    if (payload.type === 'error' && typeof payload.error === 'string') {
      return {
        type: 'error',
        error: payload.error,
        message: payload.message || null,
        limitType: payload.limit_type || null,
        limit: payload.limit ?? null,
        used: payload.used ?? null,
      };
    }
    if (
      payload.type === 'interview_result'
      && typeof payload.id === 'string'
    ) {
      return {
        type: 'interview_result',
        id: payload.id,
        mode: payload.mode,
        status: payload.status,
        resumeId: payload.resume_id || null,
        applicationId: payload.application_id || null,
        extracted: payload.extracted || {},
        message: payload.message || '面试结果已保存为待确认草稿。',
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function interviewControlMessageText(control) {
  if (!control || control.type !== 'error') return '';
  if (control.message) return control.message;
  if (control.error === 'fair_use_exceeded') {
    if (control.limitType === 'daily_sessions') {
      return `今天的免费面试次数已达上限（${control.used}/${control.limit}），请明天再试。`;
    }
    if (control.limitType === 'session_turns') {
      return `本次免费面试已达到 ${control.limit} 轮上限。`;
    }
    if (control.limitType === 'active_connections') {
      return '已有一个面试会话正在进行，请先关闭原会话。';
    }
    return '已达到免费面试的公平使用上限。';
  }
  if (
    control.error === 'subscription_inactive'
    || control.error === 'billing_account_missing'
  ) {
    return '面试权益暂不可用，请刷新账户状态或联系支持。';
  }
  return '面试暂不可用，请稍后重试。';
}

export function buildWebSocketAuthMessage(token, requestedUses = {}) {
  return JSON.stringify({
    type: 'auth',
    token: token || '',
    requested_uses: {
      resume_write: requestedUses.resume_write === true,
      job_recommendation: requestedUses.job_recommendation === true,
      employer_share: requestedUses.employer_share === true,
      model_improvement: requestedUses.model_improvement === true,
    },
  });
}

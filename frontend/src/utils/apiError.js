export function normalizeApiError(error, fallbackMessage = '请求失败，请稍后重试') {
  const payload = error?.response?.data || {};
  if (payload.error && typeof payload.error === 'object') {
    return {
      code: payload.error.code || 'http.error',
      message: payload.error.message || fallbackMessage,
      fields: payload.error.fields || {},
      requestId: payload.error.request_id || null,
      status: error?.response?.status || null,
    };
  }

  const detail = payload.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return {
      code: detail.error || detail.code || 'http.error',
      message: detail.message || fallbackMessage,
      fields: detail.fields || {},
      requestId: detail.request_id || null,
      status: error?.response?.status || null,
    };
  }
  return {
    code: 'http.error',
    message: typeof detail === 'string' ? detail : fallbackMessage,
    fields: {},
    requestId: null,
    status: error?.response?.status || null,
  };
}

export function getApiError(error, fallbackMessage) {
  return error?.apiError || normalizeApiError(error, fallbackMessage);
}

export function getApiErrorMessage(error, fallbackMessage) {
  return getApiError(error, fallbackMessage).message;
}

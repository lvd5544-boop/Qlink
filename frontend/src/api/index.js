import axios from 'axios';
import { normalizeApiError } from '../utils/apiError.js';

const httpBase = import.meta.env?.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: httpBase,
  withCredentials: true,
});

const AUTH_STORAGE_KEYS = ['token', 'auth_session', 'role', 'user_id'];

export function readCookie(name, cookieString = globalThis.document?.cookie || '') {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = cookieString.split(';').map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : '';
}

export function handleUnauthorizedSession(
  error,
  storage = window.localStorage,
  location = window.location,
) {
  const status = error?.response?.status;
  const requestUrl = error?.config?.url || '';
  if (
    status !== 401
    || requestUrl.includes('/auth/login')
    || (!storage.getItem('token') && !storage.getItem('auth_session'))
  ) {
    return false;
  }

  AUTH_STORAGE_KEYS.forEach((key) => storage.removeItem(key));
  const returnTo = `${location.pathname || '/'}${location.search || ''}`;
  const params = new URLSearchParams({
    reason: 'session_expired',
    returnTo,
  });
  location.assign(`/login?${params.toString()}`);
  return true;
}

/** 从 HTTP API 地址推导 WebSocket 根地址 */
export function getWsBaseUrl() {
  if (httpBase.startsWith('/')) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }
  try {
    const url = new URL(httpBase);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.origin;
  } catch {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }
}

// 请求拦截器：自动附带 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const method = String(config.method || 'get').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = readCookie('qlink_csrf');
    if (csrfToken) config.headers['X-CSRF-Token'] = csrfToken;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    error.apiError = normalizeApiError(error);
    handleUnauthorizedSession(error);
    return Promise.reject(error);
  },
);

export default api;

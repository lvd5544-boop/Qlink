import axios from 'axios';
import { normalizeApiError } from '../utils/apiError.js';

const httpBase = import.meta.env?.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: httpBase,
});

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
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    error.apiError = normalizeApiError(error);
    return Promise.reject(error);
  },
);

export default api;

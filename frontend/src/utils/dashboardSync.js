const DASHBOARD_METRICS_KEY = 'dashboard_metrics_delta';

export function notifyDashboardRefresh(deltas = {}) {
  const payload = {
    at: Date.now(),
    score_delta: deltas.score_delta ?? null,
    health_score_delta: deltas.health_score_delta ?? null,
    completeness_delta: deltas.completeness_delta ?? null,
    quantification_delta: deltas.quantification_delta ?? null,
    indicators: deltas.indicators ?? null,
  };
  localStorage.setItem(DASHBOARD_METRICS_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent('dashboard-refresh', { detail: payload }));
}

export function readDashboardDeltas(maxAgeMs = 5 * 60 * 1000) {
  try {
    const raw = localStorage.getItem(DASHBOARD_METRICS_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Date.now() - (data.at || 0) > maxAgeMs) return null;
    return data;
  } catch {
    return null;
  }
}

export function clearDashboardDeltas() {
  localStorage.removeItem(DASHBOARD_METRICS_KEY);
}

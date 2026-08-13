export const OUTCOME_SOURCE = {
  platform_observed: { label: '平台记录', color: 'blue' },
  employer_confirmed: { label: '招聘方确认', color: 'green' },
  candidate_reported: { label: '由你记录', color: 'gold' },
};

export function getOutcomeSourceConfig(source) {
  return OUTCOME_SOURCE[source] || { label: '来源待确认', color: 'default' };
}

export function formatOutcomeTime(value, locale = 'zh-CN') {
  if (!value) return '时间未记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间格式无效';
  return date.toLocaleString(locale);
}

export function normalizeOutcomeTimeline(events) {
  if (!Array.isArray(events)) return [];
  return events.filter((event) => event && event.to_status).map((event, index) => ({
    key: event.event_key || `outcome:${index}`,
    status: event.to_status,
    label: event.status_label || event.to_status,
    source: event.source,
    sourceConfig: getOutcomeSourceConfig(event.source),
    occurredAt: event.occurred_at || event.recorded_at || null,
    recordedAt: event.recorded_at || event.occurred_at || null,
    feedback: typeof event.raw_feedback === 'string' ? event.raw_feedback.trim() : '',
  }));
}

export function toLocalDateTimeInput(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

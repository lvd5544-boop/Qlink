import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getOutcomeSourceConfig,
  normalizeOutcomeTimeline,
  toLocalDateTimeInput,
} from './applicationTimeline.js';

test('outcome provenance labels keep platform, employer, and candidate sources distinct', () => {
  assert.equal(getOutcomeSourceConfig('platform_observed').label, '平台记录');
  assert.equal(getOutcomeSourceConfig('employer_confirmed').label, '招聘方确认');
  assert.equal(getOutcomeSourceConfig('candidate_reported').label, '由你记录');
});

test('timeline normalization preserves raw feedback and uses stable event keys', () => {
  const timeline = normalizeOutcomeTimeline([
    {
      event_key: 'status_history:0',
      to_status: 'interview_invited',
      status_label: '已收到面试邀请',
      source: 'candidate_reported',
      occurred_at: '2026-08-13T09:00:00Z',
      recorded_at: '2026-08-13T10:00:00Z',
      raw_feedback: '  Interview confirmed.  ',
    },
  ]);

  assert.equal(timeline.length, 1);
  assert.equal(timeline[0].key, 'status_history:0');
  assert.equal(timeline[0].sourceConfig.label, '由你记录');
  assert.equal(timeline[0].feedback, 'Interview confirmed.');
});

test('datetime-local default is minute-precision without a timezone suffix', () => {
  const value = toLocalDateTimeInput(new Date('2026-08-13T10:20:30Z'));
  assert.match(value, /^2026-08-13T\d{2}:20$/);
  assert.doesNotMatch(value, /Z$/);
});

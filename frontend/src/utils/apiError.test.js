import test from 'node:test';
import assert from 'node:assert/strict';

import { getApiErrorMessage, normalizeApiError } from './apiError.js';

test('normalizes the PR5.5 error envelope by stable code', () => {
  const normalized = normalizeApiError({
    response: {
      status: 429,
      data: {
        error: {
          code: 'billing.quota_exceeded',
          message: '本周期额度已用尽',
          fields: { feature: 'resume_coach' },
          request_id: 'request-1',
        },
      },
    },
  });
  assert.deepEqual(normalized, {
    code: 'billing.quota_exceeded',
    message: '本周期额度已用尽',
    fields: { feature: 'resume_coach' },
    requestId: 'request-1',
    status: 429,
  });
});

test('legacy detail remains readable only inside the compatibility normalizer', () => {
  assert.equal(
    getApiErrorMessage(
      { response: { data: { detail: '旧接口错误' } } },
      'fallback',
    ),
    '旧接口错误',
  );
});

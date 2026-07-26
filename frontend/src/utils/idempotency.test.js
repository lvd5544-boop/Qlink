import assert from 'node:assert/strict';
import test from 'node:test';

import { createIdempotencyTracker } from './idempotency.js';

test('same logical payload reuses its idempotency key until success', () => {
  let sequence = 0;
  const tracker = createIdempotencyTracker('resume-coach', () => `uuid-${++sequence}`);
  const first = tracker.keyFor({ resume_id: 'r1', options: { role: 'engineering' } });
  const retry = tracker.keyFor({ options: { role: 'engineering' }, resume_id: 'r1' });

  assert.equal(first, retry);
  tracker.complete(first);
  assert.notEqual(tracker.keyFor({ resume_id: 'r1', options: { role: 'engineering' } }), first);
});

test('changed payload receives a different idempotency key', () => {
  let sequence = 0;
  const tracker = createIdempotencyTracker('evidence', () => `uuid-${++sequence}`);

  const first = tracker.keyFor({ answer: 'A' });
  const changed = tracker.keyFor({ answer: 'B' });
  assert.notEqual(changed, first);
});

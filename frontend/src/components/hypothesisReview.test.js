import test from 'node:test';
import assert from 'node:assert/strict';
import { replaceHypothesisStatus } from './hypothesisReview.js';

test('hypothesis status updates issue and category projections without changing facts', () => {
  const hypothesis = { id: 'h1', status: 'hypothesis', text: '可能存在相关经历' };
  const issue = { id: 'i1', claim_ids: [], hypotheses: [hypothesis] };
  const diagnostic = { issues: [issue], categories: { capability: [issue] } };
  const updated = replaceHypothesisStatus(diagnostic, 'h1', { status: 'user_confirmed' });

  assert.equal(updated.issues[0].hypotheses[0].status, 'user_confirmed');
  assert.equal(updated.categories.capability[0].hypotheses[0].status, 'user_confirmed');
  assert.deepEqual(updated.issues[0].claim_ids, []);
  assert.equal(diagnostic.issues[0].hypotheses[0].status, 'hypothesis');
});

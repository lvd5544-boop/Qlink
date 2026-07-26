import test from 'node:test';
import assert from 'node:assert/strict';

import {
  APPLICATION_STATUS,
  CLARIFICATION_QUICK_FILTERS,
  getStatusConfig,
} from './applicationStatus.js';

test('clarification_closed uses distinct candidate and employer labels', () => {
  assert.equal(
    getStatusConfig('clarification_closed', 'candidate').text,
    '招聘方已关闭澄清',
  );
  assert.equal(
    getStatusConfig('clarification_closed', 'employer').text,
    '已关闭，候选人未说明',
  );
});

test('clarified never claims that facts were verified', () => {
  assert.equal(getStatusConfig('clarified', 'candidate').text, '已提交说明');
  assert.equal(
    getStatusConfig('clarified', 'employer').text,
    '候选人已说明，待复核',
  );
  assert.doesNotMatch(
    JSON.stringify(APPLICATION_STATUS),
    /已验证真实|无造假|确认属实/,
  );
});

test('clarification closed is available as its own quick filter', () => {
  const filter = CLARIFICATION_QUICK_FILTERS.find(
    (item) => item.value === 'clarification_closed',
  );
  assert.deepEqual(filter?.statuses, ['clarification_closed']);
});

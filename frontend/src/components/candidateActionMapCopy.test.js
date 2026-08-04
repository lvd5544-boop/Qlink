import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const source = fs.readFileSync(new URL('./CandidateActionMap.jsx', import.meta.url), 'utf8');

test('candidate action map separates immediate application work from clarification and development', () => {
  for (const label of [
    '已有事实，可立即优化',
    '需要说清楚',
    '建议提升，先由你确认',
    '现实条件需要确认',
    '暂时无法可靠判断',
    '没有写出来不等于没有能力',
  ]) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /issue\.category === 'capability'/);
  assert.match(source, /strategy\?\.can_apply_now/);
  assert.match(source, /先回答最重要的 3 个问题/);
  assert.match(source, /补充这条经历或证据/);
  assert.doesNotMatch(source, /title: '你不会'|title: '你不具备'|title: '不合格'|title: '淘汰'/);
});

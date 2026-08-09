import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const source = fs.readFileSync(new URL('./CandidateActionMap.jsx', import.meta.url), 'utf8');

test('candidate action map separates immediate application work from clarification and development', () => {
  for (const label of [
    '已有证据：可以直接使用',
    '信息不完整：需要立即追问',
    '暂未具备：生成发展任务',
    '现实约束：单独确认',
    '无法判断：请求补充信息',
    '没有写出来不等于没有能力',
  ]) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /groupIssuesByRouteState/);
  assert.doesNotMatch(source, /issue\.category === 'capability'/);
  assert.match(source, /先回答最重要的 3 个问题/);
  assert.match(source, /补充这条经历或证据/);
  assert.doesNotMatch(source, /title: '你不会'|title: '你不具备'|title: '不合格'|title: '淘汰'/);
});

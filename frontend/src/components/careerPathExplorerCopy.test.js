import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const source = fs.readFileSync(new URL('./CareerPathExplorer.jsx', import.meta.url), 'utf8');

test('career direction explorer keeps the three choices visible and enters the same job flow', () => {
  for (const label of ['当前方向', '相邻方向', '挑战方向', '选择这个示例岗位']) {
    assert.match(source, new RegExp(label));
  }
  assert.match(source, /role_relation/);
  assert.match(source, /improvement_delta/);
  assert.doesNotMatch(source, /\[\.\.\.preferred, \.\.\.rows\]/);
  assert.match(source, /onSelect\?\.\(job\.directionJobId\)/);
  assert.match(source, /暂无合适示例岗位/);
});

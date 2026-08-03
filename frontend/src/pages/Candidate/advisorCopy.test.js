import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const advisor = fs.readFileSync(new URL('./Advisor.jsx', import.meta.url), 'utf8');
const browseJobs = fs.readFileSync(new URL('./BrowseJobs.jsx', import.meta.url), 'utf8');

test('PR14 keeps the four target-role layers separate and labels inference', () => {
  for (const label of [
    '企业岗位真相源',
    '职业通用参考',
    '公司公开语境',
    '经许可市场信号',
    '事实必须带引用',
    '推断会明确标识',
  ]) {
    assert.match(advisor, new RegExp(label));
  }
  assert.match(advisor, /snapshot_hash/);
  assert.match(advisor, /source_version_id/);
  assert.match(advisor, /is_stale/);
  assert.match(browseJobs, /查看岗位画像/);
  assert.doesNotMatch(advisor, /公司人才画像|录用概率|面试概率/);
});

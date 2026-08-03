import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('PR13 UI requires target job and exposes faithful four-column workflow', () => {
  const source = readFileSync(new URL('./TargetJobOptimizationPanel.jsx', import.meta.url), 'utf8');
  for (const label of [
    '① 选择目标岗位',
    '② 多问题诊断',
    '③ 选择改进方式并预览',
    '④ 当前差距与下一步',
    '请先从上方选择一份岗位',
    '改写前后对照',
    '完成计划后的参考情景',
  ]) assert.match(source, new RegExp(label.replace(/[（）]/g, '.')));
  assert.doesNotMatch(source, /录用概率|offer概率|面试概率/iu);
  assert.match(source, /source_claim_ids/);
  assert.match(source, /confirm-facts/);
  assert.match(source, /resume-patches.*apply/);
  assert.match(source, /定位相关经历并生成改写/);
});

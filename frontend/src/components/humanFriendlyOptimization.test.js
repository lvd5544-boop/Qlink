import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('top matches support job details and one shared optimization target', () => {
  const matches = readFileSync(new URL('./TopJobMatches.jsx', import.meta.url), 'utf8');
  const workbench = readFileSync(
    new URL('../pages/Candidate/MyResumes.jsx', import.meta.url),
    'utf8',
  );
  assert.match(matches, /查看详情/);
  assert.match(matches, /用这个岗位优化/);
  assert.match(matches, /设为优化目标并返回工作台/);
  assert.match(workbench, /targetJobId={targetJobId}/);
  assert.match(workbench, /jobId={targetJobId}/);
});

test('growth plans translate enums and include steps and completion criteria', () => {
  const source = readFileSync(new URL('./ImprovementSimulationPanel.jsx', import.meta.url), 'utf8');
  assert.match(source, /预计 4–8 周/);
  assert.match(source, /每周约 3–5 小时/);
  assert.match(source, /按这个顺序完成/);
  assert.match(source, /什么情况下算完成/);
  assert.doesNotMatch(source, /时间范围：\\$\\{growthPlan\\.horizon\\}/);
});

test('coach empty state explains how to unlock a safe rewrite', () => {
  const source = readFileSync(new URL('./ResumeCoachPanel.jsx', import.meta.url), 'utf8');
  assert.match(source, /目前无法安全生成改写稿/);
  assert.match(source, /请先补充一段真实的工作或项目描述/);
  assert.doesNotMatch(source, /example_before[/]after/);
});

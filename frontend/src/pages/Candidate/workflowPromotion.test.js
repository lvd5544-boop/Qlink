import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const dashboard = fs.readFileSync(new URL('./Dashboard.jsx', import.meta.url), 'utf8');
const advisor = fs.readFileSync(new URL('./Advisor.jsx', import.meta.url), 'utf8');
const authLayout = fs.readFileSync(
  new URL('../../components/AuthLayout.jsx', import.meta.url),
  'utf8',
);

test('the primary job-seeking workflow is visible before and after sign in', () => {
  for (const label of [
    'AI 求职工作流',
    '把目标岗位，变成一份更能打的申请方案',
    '开始我的求职工作流',
    '选目标岗位',
    '对照真实履历',
    '生成可投方案',
  ]) {
    assert.match(dashboard, new RegExp(label));
  }
  assert.match(authLayout, /从岗位要求到可投版本/);
  assert.match(authLayout, /不再在一堆 AI 工具之间来回切换/);
  assert.match(authLayout, /选岗位 → 对照简历 → 生成可投方案/);
});

test('external JD CTA opens the advisor import flow directly', () => {
  assert.match(dashboard, /\/candidate\/advisor\?import=1/);
  assert.match(advisor, /searchParams\.get\('import'\) === '1'/);
});

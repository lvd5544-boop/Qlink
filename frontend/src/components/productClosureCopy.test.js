import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const interview = fs.readFileSync(new URL('./StructuredInterviewPanel.jsx', import.meta.url), 'utf8');
const graph = fs.readFileSync(new URL('./CareerGraph.jsx', import.meta.url), 'utf8');
const analytics = fs.readFileSync(
  new URL('../pages/Candidate/Analytics.jsx', import.meta.url),
  'utf8',
);

test('structured interview keeps history, transcript and actionable feedback', () => {
  for (const label of ['面试记录', 'AI 面试反馈', '优势', '薄弱点', '个性化训练计划', '马上练一遍', '做到什么算完成', '查看完整问答记录']) {
    assert.match(interview, new RegExp(label));
  }
  assert.match(interview, /\/interview-sessions\?limit=20/);
});

test('target-job graph explains node roles instead of showing an opaque core count', () => {
  assert.match(graph, /项岗位要求/);
  assert.match(graph, /条相关经历/);
  assert.match(graph, /简历中暂未定位，建议澄清/);
  assert.doesNotMatch(graph, /个核心节点/);
});

test('market insight falls back to cross-company open JDs', () => {
  assert.match(analytics, /同类岗位通常看重什么/);
  assert.match(analytics, /以下展示同类岗位的常见要求/);
  assert.match(analytics, /不代表这家公司的硬性标准/);
});

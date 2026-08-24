import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const layout = fs.readFileSync(
  new URL('../../components/CandidateLayout.jsx', import.meta.url),
  'utf8',
);
const jobs = fs.readFileSync(new URL('./JobList.jsx', import.meta.url), 'utf8');
const passport = fs.readFileSync(new URL('./CareerPassport.jsx', import.meta.url), 'utf8');
const advisor = fs.readFileSync(new URL('./Advisor.jsx', import.meta.url), 'utf8');
const analytics = fs.readFileSync(new URL('./Analytics.jsx', import.meta.url), 'utf8');

test('candidate navigation uses task language and promotes the primary workflow', () => {
  for (const label of ['找岗位', '优化简历', 'AI 面试', '投递进度', '更多']) {
    assert.match(layout, new RegExp(label));
  }
  assert.match(layout, /AI 求职工作流/);
  assert.match(layout, /主推/);
  assert.match(layout, /key: '\/candidate\/advisor'/);
  assert.doesNotMatch(layout, /journey=\{/);
});

test('job recommendations show decisions first and keep technical references optional', () => {
  assert.match(jobs, /jobs\.slice\(0, visibleCount\)/);
  assert.match(jobs, /查看更多岗位/);
  assert.match(jobs, /查看推荐参考（可选）/);
  assert.doesNotMatch(jobs, /评分方法放在详情里/);
  assert.doesNotMatch(jobs, /MatchBreakdownPreview|ClickableScoreTag/);
});

test('career memory and advisor keep advanced system details collapsed', () => {
  assert.match(passport, /我的成长与能力图/);
  assert.match(passport, /查看修改记录（可选）/);
  assert.match(passport, /你的经历/);
  assert.match(advisor, /查看职业参考、公司背景和信息来源（可选）/);
  assert.match(advisor, /你现在最该做什么/);
});

test('candidate market reference hides developer methodology and contribution controls', () => {
  assert.doesNotMatch(
    analytics,
    /方法论与数据来源|网络帖样本|模型置信度|Laplace|Wilson|补充参考（低权重）|演示语料/,
  );
  assert.match(analytics, /同类岗位通常看重什么/);
  assert.match(analytics, /暂时没有足够信息。可以更换公司或岗位方向。/);
});

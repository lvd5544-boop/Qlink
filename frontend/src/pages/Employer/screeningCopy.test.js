import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const screening = fs.readFileSync(new URL('./Screening.jsx', import.meta.url), 'utf8');
const credibility = fs.readFileSync(
  new URL('../../components/ResumeCredibilityPanel.jsx', import.meta.url),
  'utf8',
);

test('PR15 screening UI forbids score and auto-reject wording', () => {
  for (const label of [
    '硬条件',
    '人工复核',
    '合理替代解释',
    '建议追问',
    '结构化决策路径',
    '最终去留由人工决定',
  ]) {
    assert.match(screening, new RegExp(label));
  }
  assert.doesNotMatch(screening, /可信度分数|造假概率|测谎|风险指数/);
  assert.doesNotMatch(screening, /自动淘汰/);
  assert.doesNotMatch(credibility, /风险指数\s*\{|可信度分数|造假概率|测谎/);
  assert.match(credibility, /批筛复核/);
  assert.match(screening, /不使用风险分/);
  assert.match(screening, /招聘方在岗位发布时确认的必须满足条件/);
  assert.match(screening, /暂无已授权申请，收到新申请后可再次海选/);
  assert.doesNotMatch(screening, /keyword\.trim\(\)\s*\|\|\s*['"]Python/);
  assert.doesNotMatch(screening, /JSON\.stringify\(selected\.decision_trace/);
});

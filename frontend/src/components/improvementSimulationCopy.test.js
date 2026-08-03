import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('PR9 UI labels a simulation and never promises hiring outcomes', () => {
  const source = readFileSync(new URL('./ImprovementSimulationPanel.jsx', import.meta.url), 'utf8');
  for (const label of ['现在可以优化', '需要补充证据', '需要真实提升', '硬门槛', '模型内模拟，不代表面试或录用承诺。']) assert.match(source, new RegExp(label));
  assert.match(source, /open_evidence_followup: '补充证据'/);
  assert.match(source, /open_claim_passport: '查看主张'/);
  assert.match(source, /onAction\(option, issue\)/);
  assert.match(source, /选择已更改，等待重新模拟/);
  assert.match(source, /策略组合已经更新；本次调整与其他已选策略效果重叠/);
  assert.match(source, /当前策略状态：/);
  assert.match(source, /当前策略组合：/);
  assert.match(source, /已重新模拟，尚未标记/);
  assert.match(source, /补证后才计分/);
  assert.match(source, /与其他策略重叠或当前不影响计分/);
  assert.match(source, /本次计分/);
  assert.doesNotMatch(source, /录用概率|offer概率|面试概率/iu);
});

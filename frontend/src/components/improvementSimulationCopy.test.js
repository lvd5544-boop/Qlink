import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('PR9 UI labels a simulation and never promises hiring outcomes', () => {
  const source = readFileSync(new URL('./ImprovementSimulationPanel.jsx', import.meta.url), 'utf8');
  for (const label of ['现在可以优化', '需要补充证据', '需要真实提升', '硬门槛', '模型内模拟，不代表面试或录用承诺。']) assert.match(source, new RegExp(label));
  assert.doesNotMatch(source, /录用概率|offer概率|面试概率/iu);
});

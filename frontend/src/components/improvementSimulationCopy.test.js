import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('PR9 UI presents actions without exposing scoring mechanics or promising outcomes', () => {
  const source = readFileSync(new URL('./ImprovementSimulationPanel.jsx', import.meta.url), 'utf8');
  for (const label of ['现在可以优化', '需要补充证据', '需要真实提升', '需要先确认的要求', '这不是面试或录用预测']) assert.match(source, new RegExp(label));
  assert.match(source, /open_evidence_followup: '补充证据'/);
  assert.match(source, /open_claim_passport: '查看主张'/);
  assert.match(source, /onAction\(option, issue\)/);
  assert.match(source, /选择已更改，等待更新/);
  assert.match(source, /新的准备顺序已经保存/);
  assert.match(source, /当前策略状态：/);
  assert.match(source, /当前行动：/);
  assert.match(source, /方案已更新，尚未标记/);
  assert.match(source, /先补充真实材料/);
  assert.match(source, /与其他行动作用相近/);
  assert.match(source, /会改变准备建议/);
  assert.doesNotMatch(source, /potential_score|marginal_delta|toFixed\(2\)/);
  assert.doesNotMatch(source, /录用概率|offer概率|面试概率/iu);
});

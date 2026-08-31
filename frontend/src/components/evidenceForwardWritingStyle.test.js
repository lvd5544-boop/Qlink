import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('evidence follow-up uses the evidence-forward writing contract', () => {
  const source = readFileSync(new URL('./EvidenceFollowupModal.jsx', import.meta.url), 'utf8');

  assert.match(source, /style_template: 'evidence_forward'/);
  assert.match(source, /动作 \+ 任务 \+ 方法\/范围 \+ 已证实结果/);
  assert.match(source, /不会编造未提及的事实/);
  assert.match(source, /来源追溯/);
  assert.match(source, /写作风格：/);
});

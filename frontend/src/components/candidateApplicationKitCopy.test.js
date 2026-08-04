import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('./CandidateApplicationKit.jsx', import.meta.url), 'utf8');

test('application kit exports only existing material and makes provenance limits explicit', () => {
  assert.match(source, /只整理已有事实/);
  assert.match(source, /evidence_state !== 'conflict_detected'/);
  assert.match(source, /求职信素材结构/);
  assert.match(source, /面试故事提纲（STAR）/);
  assert.match(source, /下载 TXT 素材包/);
  assert.doesNotMatch(source, /保证|录用概率|自动投递/);
});

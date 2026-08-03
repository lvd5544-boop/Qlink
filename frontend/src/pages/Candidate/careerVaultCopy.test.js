import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const passport = fs.readFileSync(new URL('./CareerPassport.jsx', import.meta.url), 'utf8');
const vault = fs.readFileSync(new URL('./EvidenceVault.jsx', import.meta.url), 'utf8');

test('career memory merges timeline, capability and evidence into one user-facing graph', () => {
  assert.match(passport, /我的成长与能力图/);
  assert.match(passport, /view="unified"/);
  assert.match(passport, /\['timeline', 'capability', 'evidence'\]/);
  assert.doesNotMatch(passport, /MAP_VIEWS|<Tabs/);
  assert.match(passport, /不等于第三方事实认证/);
  assert.doesNotMatch(passport, /可信度分数|造假概率|测谎/);
});

test('Evidence Vault has withdrawal and mobile-friendly list fallback copy', () => {
  assert.match(vault, /撤回后不会进入新的改写/);
  assert.match(vault, /<List/);
  assert.match(vault, /仅自己/);
  assert.match(vault, /无需为了使用职业档案而上传材料/);
  assert.match(vault, /\.py,.ipynb/);
});

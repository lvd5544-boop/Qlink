import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const candidatePanel = readFileSync(
  fileURLToPath(new URL('./ClaimPassportPanel.jsx', import.meta.url)),
  'utf8',
);
const employerPanel = readFileSync(
  fileURLToPath(new URL('./ApplicationClaimPassportPanel.jsx', import.meta.url)),
  'utf8',
);

test('Claim Passport copy describes provenance and never a fact certification', () => {
  const copy = `${candidatePanel}\n${employerPanel}`;
  assert.match(copy, /不代表事实已认证/);
  assert.match(copy, /有用户证据支持/);
  assert.match(copy, /存在冲突/);
  assert.doesNotMatch(copy, /已验证真实|认证通过|确认属实|无造假/);
});

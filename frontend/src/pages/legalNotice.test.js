import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const register = fs.readFileSync(new URL('./Register.jsx', import.meta.url), 'utf8');
const notice = fs.readFileSync(new URL('./LegalNotice.jsx', import.meta.url), 'utf8');

test('registration requires separate terms and privacy acknowledgements', () => {
  assert.match(register, /name="privacy_notice_acknowledged"/);
  assert.match(register, /name="terms_accepted"/);
  assert.match(register, /valuePropName="checked"/);
  assert.match(register, /to="\/privacy"/);
  assert.match(register, /to="\/terms"/);
});

test('public notices preserve the product and model-consent boundaries', () => {
  assert.match(notice, /不是招聘决定系统、职业结果保证或自动投递服务/);
  assert.match(notice, /模型改进是独立授权，默认关闭/);
  assert.match(notice, /AI 推断不会自动成为你的事实/);
  assert.match(notice, /\/auth\/legal-notice/);
});

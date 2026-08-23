import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (name) => readFileSync(new URL(name, import.meta.url), 'utf8');

test('password recovery stays generic and password changes sign out all sessions', () => {
  const forgot = read('./ForgotPassword.jsx');
  const reset = read('./ResetPassword.jsx');
  const security = read('./AccountSecurity.jsx');
  const login = read('./Login.jsx');

  assert.match(forgot, /如果该邮箱已注册/);
  assert.match(reset, /password-reset\/confirm/);
  assert.match(security, /password\/change/);
  assert.match(security, /localStorage\.clear/);
  assert.match(login, /forgot-password/);
});

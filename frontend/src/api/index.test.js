import assert from 'node:assert/strict';
import test from 'node:test';

import { getWsBaseUrl, handleUnauthorizedSession, readCookie } from './index.js';


test('production default WebSocket URL stays on the current origin', () => {
  globalThis.window = {
    location: {
      protocol: 'https:',
      host: 'jobs.example.cn',
    },
    localStorage: {
      getItem: () => null,
    },
  };
  assert.equal(getWsBaseUrl(), 'wss://jobs.example.cn');
  delete globalThis.window;
});

test('expired authenticated session is cleared and redirected to login', () => {
  const values = new Map([
    ['auth_session', '1'],
    ['role', 'candidate'],
    ['user_id', 'candidate-1'],
  ]);
  let assigned = null;
  const handled = handleUnauthorizedSession(
    {
      response: { status: 401 },
      config: { url: '/parse-resume' },
    },
    {
      getItem: (key) => values.get(key) || null,
      removeItem: (key) => values.delete(key),
    },
    {
      pathname: '/candidate/upload-resume',
      search: '',
      assign: (value) => { assigned = value; },
    },
  );

  assert.equal(handled, true);
  assert.equal(values.has('token'), false);
  assert.equal(values.has('auth_session'), false);
  assert.equal(
    assigned,
    '/login?reason=session_expired&returnTo=%2Fcandidate%2Fupload-resume',
  );
});

test('CSRF cookie parsing is exact and URL decoded', () => {
  assert.equal(readCookie('qlink_csrf', 'other=x; qlink_csrf=a%2Bb; qlink_csrf_old=no'), 'a+b');
  assert.equal(readCookie('missing', 'qlink_csrf=value'), '');
});

test('login failure does not trigger the expired-session redirect', () => {
  const handled = handleUnauthorizedSession(
    {
      response: { status: 401 },
      config: { url: '/auth/login' },
    },
    {
      getItem: () => 'existing-token',
      removeItem: () => assert.fail('must not clear login state here'),
    },
    {
      pathname: '/login',
      search: '',
      assign: () => assert.fail('must not redirect a failed login'),
    },
  );

  assert.equal(handled, false);
});

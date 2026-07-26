import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildInterviewWsUrl,
  buildWebSocketAuthMessage,
  interviewControlMessageText,
  isWebSocketAuthOk,
  parseInterviewControlMessage,
} from './interviewWebSocket.js';

test('interview websocket URL never contains the access token', () => {
  const url = buildInterviewWsUrl(
    'wss://app.example.test',
    'candidate-1',
    {
      mode: 'claim_followup',
      resumeId: 'resume-1',
      applicationId: 'application-1',
      token: 'long-lived-secret-token',
    },
  );
  assert.doesNotMatch(url, /token|long-lived-secret-token/);
  assert.match(url, /resume_id=resume-1/);
  assert.match(url, /application_id=application-1/);
});

test('only the explicit auth_ok envelope completes authentication', () => {
  assert.equal(isWebSocketAuthOk('{"type":"auth_ok"}'), true);
  assert.equal(isWebSocketAuthOk('欢迎开始面试'), false);
  assert.equal(isWebSocketAuthOk('{"type":"message"}'), false);
});

test('the first websocket payload is an explicit auth envelope', () => {
  assert.deepEqual(
    JSON.parse(buildWebSocketAuthMessage('access-token', {
      resume_write: true,
      model_improvement: false,
    })),
    {
      type: 'auth',
      token: 'access-token',
      requested_uses: {
        resume_write: true,
        job_recommendation: false,
        employer_share: false,
        model_improvement: false,
      },
    },
  );
});

test('fair-use websocket errors are structured and user-readable', () => {
  const control = parseInterviewControlMessage(JSON.stringify({
    type: 'error',
    error: 'fair_use_exceeded',
    limit_type: 'session_turns',
    limit: 50,
    used: 50,
  }));
  assert.deepEqual(control, {
    type: 'error',
    error: 'fair_use_exceeded',
    message: null,
    limitType: 'session_turns',
    limit: 50,
    used: 50,
  });
  assert.equal(
    interviewControlMessageText(control),
    '本次免费面试已达到 50 轮上限。',
  );
});

test('interview result is parsed as a consent control message', () => {
  const control = parseInterviewControlMessage(JSON.stringify({
    type: 'interview_result',
    id: 'result-1',
    mode: 'claim_followup',
    status: 'pending_confirmation',
    resume_id: 'resume-1',
    application_id: 'application-1',
    extracted: { answers: [{ answer: 'example' }] },
    message: '请确认用途',
  }));
  assert.deepEqual(control, {
    type: 'interview_result',
    id: 'result-1',
    mode: 'claim_followup',
    status: 'pending_confirmation',
    resumeId: 'resume-1',
    applicationId: 'application-1',
    extracted: { answers: [{ answer: 'example' }] },
    message: '请确认用途',
  });
});

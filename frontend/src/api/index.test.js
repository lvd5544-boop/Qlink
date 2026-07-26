import assert from 'node:assert/strict';
import test from 'node:test';

import { getWsBaseUrl } from './index.js';


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

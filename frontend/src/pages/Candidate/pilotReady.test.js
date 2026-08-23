import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const pilot = fs.readFileSync(new URL('./PilotHub.jsx', import.meta.url), 'utf8');
const help = fs.readFileSync(new URL('../Help.jsx', import.meta.url), 'utf8');
const login = fs.readFileSync(new URL('../Login.jsx', import.meta.url), 'utf8');

test('pilot consent is reversible and model improvement is separately optional', () => {
  assert.match(pilot, /模型改进默认关闭/);
  assert.match(pilot, /model_improvement/);
  assert.match(pilot, /退出 pilot \/ Withdraw/);
  assert.match(pilot, /不会替你自动提交申请/);
});

test('pilot page exposes feedback and explicit account deletion confirmation', () => {
  assert.match(pilot, /\/pilot\/feedback/);
  assert.match(pilot, /deletePhrase !== '删除我的账号'/);
  assert.match(pilot, /api\.delete\('\/auth\/account'\)/);
});

test('help copy preserves candidate confirmation boundary', () => {
  assert.doesNotMatch(help, /并自动更新您的简历画像/);
  assert.match(help, /只有你明确确认的内容才能成为个人事实/);
});

test('successful account deletion has a visible completion message', () => {
  assert.match(login, /reason === 'account_deleted'/);
  assert.match(login, /账号及关联私有数据已删除/);
});

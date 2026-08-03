import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./Dashboard.jsx', import.meta.url), 'utf8');
const uploadResume = readFileSync(new URL('./UploadResume.jsx', import.meta.url), 'utf8');
const myResumes = readFileSync(new URL('./MyResumes.jsx', import.meta.url), 'utf8');

test('candidate dashboard opens My Resumes from the resume statistic card', () => {
  assert.match(dashboard, /aria-label="打开我的简历"/);
  assert.match(dashboard, /navigate\('\/candidate\/my-resumes'\)/);
});

test('resume upload displays the actionable API error instead of hiding it', () => {
  assert.match(uploadResume, /getApiErrorMessage\(error, '简历解析失败，请稍后重试'\)/);
  assert.doesNotMatch(uploadResume, /\.catch\(\(\) => message\.error\('解析失败'\)\)/);
});

test('simulation evidence actions focus and explain the Claim Passport destination', () => {
  assert.match(myResumes, /setPassportFocus\(/);
  assert.match(myResumes, /getElementById\('claim-passport'\)/);
  assert.match(myResumes, /当前问题未关联到现有主张/);
});

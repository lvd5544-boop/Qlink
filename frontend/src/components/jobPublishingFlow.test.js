import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  buildRequirementChoices,
  confirmationPayload,
  formToJob,
} from './jobProfileEditorUtils.js';

const postJob = fs.readFileSync(
  new URL('../pages/Employer/PostJob.jsx', import.meta.url),
  'utf8',
);
const screening = fs.readFileSync(
  new URL('../pages/Employer/Screening.jsx', import.meta.url),
  'utf8',
);
const profileEditor = fs.readFileSync(
  new URL('./JobProfileEditor.jsx', import.meta.url),
  'utf8',
);

test('job requirements default to reviewable priorities, never implicit hard filters', () => {
  const choices = buildRequirementChoices({
    responsibilities: '建设 API',
    required_skills: 'Python, SQL',
    experience_years: 3,
    location: '上海',
  });
  assert.equal(choices.length, 5);
  assert.equal(choices.find((item) => item.text === 'Python').classification, 'preferred');
  assert.equal(choices.find((item) => item.text === '3 年相关经验').classification, 'preferred');
  assert.equal(choices.find((item) => item.text === '上海').classification, 'context');
  assert.equal(choices.some((item) => item.classification === 'hard'), false);
});

test('explicit employer choices map to the current server profile', () => {
  const choices = buildRequirementChoices({ required_skills: 'Python, SQL' });
  choices[0].classification = 'hard';
  const payload = confirmationPayload({
    layers: {
      target_role: {
        requirements: [
          { id: 'r-python', type: 'skill', text: 'Python' },
          { id: 'r-sql', type: 'skill', text: 'SQL' },
        ],
      },
    },
  }, choices);
  assert.deepEqual(payload, [
    { requirement_id: 'r-python', classification: 'hard' },
    { requirement_id: 'r-sql', classification: 'preferred' },
  ]);
});

test('employer workflow publishes once and screening starts in one action', () => {
  assert.match(postJob, /岗位草稿已生成/);
  assert.match(profileEditor, /确认要求并发布岗位/);
  assert.match(postJob, /profile\/confirm/);
  assert.match(screening, /开始海选/);
  assert.match(screening, /批量标记已复核/);
  assert.doesNotMatch(screening, /创建批筛并配置规则|>执行批筛<|addonBefore="合规依据"/);
});

test('employer profile cannot configure school-prestige keywords', () => {
  assert.doesNotMatch(profileEditor, /school_tier_keywords|学校层级关键词/);
  const payload = formToJob(
    { title: 'Backend Engineer', required_skills: 'Python' },
    { school_tier_keywords: ['985'], publication_status: 'draft' },
  );
  assert.equal(Object.hasOwn(payload, 'school_tier_keywords'), false);
});

import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const source = fs.readFileSync(new URL('./MyResumes.jsx', import.meta.url), 'utf8');
const optimization = fs.readFileSync(new URL('../../components/TargetJobOptimizationPanel.jsx', import.meta.url), 'utf8');

test('resume workbench preserves a target job passed from the advisor, including a private imported JD', () => {
  assert.match(source, /searchParams\.get\('jobId'\)/);
  assert.match(source, /setTargetJobId\(requestedJobId\)/);
  assert.match(source, /已带入目标岗位/);
  assert.doesNotMatch(source, /requestedJobId.*topMatches\.find/);
  assert.match(optimization, /`\/advisor\/jobs\/\$\{targetJobId\}\/profile`/);
  assert.match(optimization, /privateJob.*\[privateJob, \.\.\.rows\]/s);
});

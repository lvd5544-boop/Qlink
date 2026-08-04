import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const advisor = fs.readFileSync(new URL('./Advisor.jsx', import.meta.url), 'utf8');
const browseJobs = fs.readFileSync(new URL('./BrowseJobs.jsx', import.meta.url), 'utf8');

test('PR14 keeps the four target-role layers separate and labels inference', () => {
  for (const label of [
    '企业岗位真相源',
    '职业通用参考',
    '公司公开语境',
    '经许可市场信号',
    '事实必须带引用',
    '推断会明确标识',
  ]) {
    assert.match(advisor, new RegExp(label));
  }
  assert.match(advisor, /snapshot_hash/);
  assert.match(advisor, /source_version_id/);
  assert.match(advisor, /is_stale/);
  assert.match(browseJobs, /查看岗位画像/);
  assert.doesNotMatch(advisor, /公司人才画像|录用概率|面试概率/);
});

test('candidate can import a real private JD before asking for grounded guidance', () => {
  for (const label of [
    '粘贴目标 JD',
    '粘贴你真正想申请的岗位',
    'JD 只用于理解目标岗位',
    '不会把岗位要求当成你的经历',
    '不会把你导入的岗位公开到岗位列表',
  ]) {
    assert.match(advisor, new RegExp(label));
  }
  assert.match(advisor, /['"]\/advisor\/target-jobs\/import['"]/);
  assert.match(advisor, /description_text: descriptionText/);
  assert.match(advisor, /setJobs\(\(current\) => \[/);
});

test('advisor carries the selected resume and target job into the existing application workbench', () => {
  assert.match(advisor, /new URLSearchParams\(\{ resumeId: selectedResumeId, jobId \}\)/);
  assert.match(advisor, /生成当前可投版本并安排提升行动/);
  assert.match(advisor, /查看投递、面试和录用结果/);
  assert.match(advisor, /改写只使用你已确认的履历事实/);
});

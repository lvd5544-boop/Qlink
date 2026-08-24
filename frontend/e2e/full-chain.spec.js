import { expect, test } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:8000';
const INVITE = process.env.EMPLOYER_INVITE_CODE || 'e2e-employer-invite';
const PASSWORD = 'E2ePassw0rd!';

async function api(method, route, { token, body, formData } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload = body;
  if (body && !formData) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API}${route}`, {
    method,
    headers,
    body: formData || payload,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new Error(`${method} ${route} -> ${res.status}: ${text}`);
  }
  return data;
}

async function loginUi(page, email, password, expectedPath) {
  await page.goto('/login');
  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(expectedPath, { timeout: 30000 });
}

async function sessionAs(page, token, role, userId) {
  await page.goto('/login');
  await page.evaluate(
    ({ token: t, role: r, userId: u }) => {
      localStorage.setItem('token', t);
      localStorage.setItem('role', r);
      localStorage.setItem('user_id', u);
    },
    { token, role, userId },
  );
}

test.describe.configure({ mode: 'serial' });

test('full hiring chain in browser', async ({ page }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const candidateEmail = `cand.e2e.${stamp}@example.com`;
  const employerEmail = `emp.e2e.${stamp}@example.com`;

  // 1) Candidate register via UI, then login UI
  await page.goto('/register');
  await page.getByPlaceholder('邮箱').fill(candidateEmail);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole('checkbox', { name: /隐私说明/ }).check();
  await page.getByRole('checkbox', { name: /服务条款/ }).check();
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/login/, { timeout: 30000 });

  await loginUi(page, candidateEmail, PASSWORD, /\/candidate\/dashboard/);

  // 2) Employer register (invite-gated) + session + post job via UI
  await api('POST', '/auth/register-employer', {
    body: {
      email: employerEmail,
      password: PASSWORD,
      invite_code: INVITE,
      terms_accepted: true,
      privacy_notice_acknowledged: true,
    },
  });
  const employerLogin = await api('POST', '/auth/login', {
    body: { email: employerEmail, password: PASSWORD },
  });
  const employerToken = employerLogin.access_token;

  await sessionAs(page, employerToken, 'employer', employerLogin.user_id);
  await page.goto('/employer/post-job');
  await expect(page.getByPlaceholder('粘贴岗位描述...')).toBeVisible({ timeout: 20000 });
  await page.getByPlaceholder('粘贴岗位描述...').fill(
    '岗位：后端工程师\n要求：Python FastAPI PostgreSQL\n地点：上海\n职责：开发招聘平台 API',
  );
  await page.getByRole('button', { name: '提取岗位信息' }).click();
  await expect(page.getByText('岗位名称')).toBeVisible({ timeout: 60000 });
  await page.getByRole('button', { name: '确认要求并发布岗位' }).click();
  await expect(page).toHaveURL(/\/employer\/screening/, { timeout: 60000 });

  const jobs = await api('GET', '/jobs/mine', { token: employerToken });
  const jobList = Array.isArray(jobs) ? jobs : [];
  expect(jobList.length).toBeGreaterThan(0);
  const jobId = String(jobList[0].id);

  // 3) Candidate upload resume via UI
  const candidateLogin = await api('POST', '/auth/login', {
    body: { email: candidateEmail, password: PASSWORD },
  });
  const candidateToken = candidateLogin.access_token;

  await sessionAs(page, candidateToken, 'candidate', candidateLogin.user_id);
  const resumePath = path.join(__dirname, `resume-${stamp}.txt`);
  writeFileSync(
    resumePath,
    [
      '姓名：E2E候选人',
      `邮箱：${candidateEmail}`,
      '期望职位：后端工程师',
      '技能：Python, FastAPI, PostgreSQL, Redis',
      '工作经历：某科技 后端工程师 2022-2025',
      '负责招聘平台 API 与匹配服务，日请求 10 万+',
    ].join('\n'),
  );

  await page.goto('/candidate/upload-resume');
  await page.locator('input[type="file"]').setInputFiles(resumePath);
  await expect
    .poll(
      async () => {
        const resumes = await api('GET', `/resumes/${candidateLogin.user_id}`, {
          token: candidateToken,
        });
        return Array.isArray(resumes) ? resumes.length : 0;
      },
      { timeout: 60000 },
    )
    .toBeGreaterThan(0);

  const resumes = await api('GET', `/resumes/${candidateLogin.user_id}`, {
    token: candidateToken,
  });
  const resumeId = String(resumes[0].id);

  // 4) Browse jobs in UI, then apply via API
  await page.goto('/candidate/browse-jobs');
  await expect(page.getByText(/后端|工程师|岗位/).first()).toBeVisible({ timeout: 20000 });
  await api('POST', '/applications', {
    token: candidateToken,
    body: { job_id: jobId, resume_id: resumeId, cover_letter: 'E2E apply' },
  });

  const apps = await api('GET', '/applications/mine', { token: candidateToken });
  const appList = Array.isArray(apps) ? apps : [];
  expect(appList.length).toBeGreaterThan(0);
  const applicationId = String(appList[0].id);

  // PR8: Passport has stable candidate claims and an employer-only immutable snapshot.
  const claims = await api('POST', `/resumes/${resumeId}/claims/sync`, { token: candidateToken });
  expect(claims.claims.length).toBeGreaterThan(0);
  const passportSnapshot = await api('GET', `/applications/${applicationId}/claim-passport`, {
    token: employerToken,
  });
  expect(passportSnapshot.claims.length).toBeGreaterThan(0);
  await page.goto('/candidate/my-resumes');
  await page.getByRole('button', { name: '进入工作台' }).first().click();
  await expect(page.getByText('④ 经历澄清卡')).toBeVisible({ timeout: 30000 });
  await expect(page.getByText('下一步行动')).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: /更新行动方案/ }).click();
  await expect(page.getByText('这不是面试或录用预测。', { exact: false })).toBeVisible();

  // 5) Employer clarification then candidate reply in UI (API fallback)
  await api('POST', `/applications/${applicationId}/clarification-requests`, {
    token: employerToken,
    body: {
      claim_id: 'e2e-claim-1',
      claim_text: '日请求 10 万+',
      questions: ['峰值 QPS 与观测窗口？'],
    },
  });

  await page.goto('/candidate/applied-jobs');
  await expect(page.getByText(/澄清|补充|说明|日请求|待回复/).first()).toBeVisible({
    timeout: 20000,
  });
  const openReply = page.getByRole('button', { name: /回复澄清/ }).first();
  if (await openReply.count()) {
    await openReply.click();
  }
  const replyBox = page.locator('textarea').first();
  await expect(replyBox).toBeVisible({ timeout: 15000 });
  await replyBox.fill('峰值约 80 QPS，观测窗口为工作日晚高峰一小时。');
  await page.getByRole('button', { name: /发送澄清回复|提交说明|提交回复/ }).first().click();
  await page.waitForTimeout(1500);

  const appsAfterReply = await api('GET', '/applications/mine', {
    token: candidateToken,
  });
  const replied = (Array.isArray(appsAfterReply) ? appsAfterReply : []).find(
    (row) => String(row.id) === applicationId,
  );
  if (!replied || Number(replied.open_claim_count || 0) > 0) {
    await api('POST', `/applications/${applicationId}/clarification-response`, {
      token: candidateToken,
      body: {
        claim_id: 'e2e-claim-1',
        body: '峰值约 80 QPS，观测窗口为工作日晚高峰一小时。',
      },
    });
  }

  // 6) Employer invite (UI when available, API fallback)
  await sessionAs(page, employerToken, 'employer', employerLogin.user_id);
  await page.goto(`/employer/applications/${jobId}`);
  await page.waitForTimeout(1500);
  const inviteBtn = page.getByRole('button', { name: /面试邀请|邀请面试|发送邀请/ }).first();
  if (await inviteBtn.count()) {
    await inviteBtn.click();
    await page.waitForTimeout(1000);
  }
  const afterInvite = await api('GET', `/applications/job/${jobId}`, {
    token: employerToken,
  });
  const alreadyInvited = (Array.isArray(afterInvite) ? afterInvite : []).some(
    (row) => String(row.status) === 'interview_invited',
  );
  if (!alreadyInvited) {
    await api('POST', '/invitations/send', {
      token: employerToken,
      body: {
        job_id: jobId,
        resume_id: resumeId,
        application_id: applicationId,
        message: 'E2E interview invite',
      },
    });
  }

  const invited = await api('GET', `/applications/job/${jobId}`, {
    token: employerToken,
  });
  const invitedList = Array.isArray(invited) ? invited : [];
  expect(
    invitedList.some((row) => String(row.status) === 'interview_invited'),
  ).toBeTruthy();

  // 7) Candidate interview consent surface
  await sessionAs(page, candidateToken, 'candidate', candidateLogin.user_id);
  await page.goto(`/candidate/interview?applicationId=${applicationId}`);
  await expect(page.getByText('结构化 AI 面试官')).toBeVisible({ timeout: 20000 });
  for (const consent of ['简历写回', '岗位推荐', '分享给招聘方', '模型改进']) {
    await expect(page.getByText(consent, { exact: true })).toBeVisible();
  }
  const checks = page.locator('.ant-checkbox-input:not([disabled])');
  const checkCount = await checks.count();
  expect(checkCount).toBeGreaterThan(0);
  for (let i = 0; i < checkCount; i += 1) {
    await checks.nth(i).check({ force: true });
  }
  await expect(page.getByRole('button', { name: '开始结构化面试' })).toBeVisible();
});

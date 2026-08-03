import { expect, test } from '@playwright/test';

const API = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:8000';
const PASSWORD = 'E2ePassw0rd!';
const INVITE = process.env.EMPLOYER_INVITE_CODE || 'local-employer-invite';

async function api(method, route, { token, body, headers = {}, form } = {}) {
  const requestHeaders = { ...headers };
  if (token) requestHeaders.Authorization = `Bearer ${token}`;
  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const response = await fetch(`${API}${route}`, {
    method,
    headers: requestHeaders,
    body: payload,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(`${method} ${route} -> ${response.status}: ${text}`);
  }
  return data;
}

async function sessionAs(page, token, userId, role) {
  await page.goto('/login');
  await page.evaluate(
    ({ accessToken, id, userRole }) => {
      localStorage.setItem('token', accessToken);
      localStorage.setItem('role', userRole);
      localStorage.setItem('user_id', id);
    },
    { accessToken: token, id: userId, userRole: role },
  );
}

test('PR15 employer screening layered results without risk score', async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const employerEmail = `emp.pr15.${stamp}@example.com`;
  const candidateEmail = `cand.pr15.${stamp}@example.com`;

  await api('POST', '/auth/register-employer', {
    body: { email: employerEmail, password: PASSWORD, invite_code: INVITE },
  });
  const employerLogin = await api('POST', '/auth/login', {
    body: { email: employerEmail, password: PASSWORD },
  });
  await api('POST', '/auth/register', {
    body: { email: candidateEmail, password: PASSWORD, role: 'candidate' },
  });
  const candidateLogin = await api('POST', '/auth/login', {
    body: { email: candidateEmail, password: PASSWORD },
  });

  const jd = encodeURIComponent(
    '岗位：PR15 Backend Engineer\n要求技能：Python, SQL\n地点：上海\n职责：建设后端 API',
  );
  const posted = await api('POST', `/post-job?description_text=${jd}`, {
    token: employerLogin.access_token,
  });
  const jobId = posted.job_id || posted.id;
  expect(jobId).toBeTruthy();
  const jobs = await api('GET', '/jobs/mine', { token: employerLogin.access_token });
  const job = (Array.isArray(jobs) ? jobs : []).find((item) => item.id === jobId) || {
    id: jobId,
  };
  expect(job?.id).toBeTruthy();

  await api('GET', `/advisor/jobs/${job.id}/profile`, {
    token: employerLogin.access_token,
  });
  await api('POST', `/advisor/jobs/${job.id}/profile/confirm`, {
    token: employerLogin.access_token,
    headers: { 'Idempotency-Key': `pr15-confirm-${stamp}` },
  });

  await sessionAs(page, candidateLogin.access_token, candidateLogin.user_id, 'candidate');
  await page.goto('/candidate/upload-resume');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'pr15-resume.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      [
        'Name: PR15 Candidate',
        `Email: ${candidateEmail}`,
        'Skills: Python, SQL',
        'Experience: Built Python APIs for 2 years',
      ].join('\n'),
    ),
  });
  await expect
    .poll(async () => {
      const rows = await api('GET', `/resumes/${candidateLogin.user_id}`, {
        token: candidateLogin.access_token,
      });
      return Array.isArray(rows) ? rows.length : 0;
    }, { timeout: 60_000 })
    .toBeGreaterThan(0);
  const resumes = await api('GET', `/resumes/${candidateLogin.user_id}`, {
    token: candidateLogin.access_token,
  });
  await api('POST', '/applications', {
    token: candidateLogin.access_token,
    body: { job_id: job.id, resume_id: resumes[0].id },
  });

  await sessionAs(page, employerLogin.access_token, employerLogin.user_id, 'employer');
  await page.goto(`/employer/screening?job_id=${job.id}`);
  await expect(page.getByText('批量初筛与人工复核')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('不使用风险分')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('风险指数');
  await expect(page.locator('body')).not.toContainText('可信度分数');

  await page.getByRole('button', { name: '开始海选' }).click();
  await expect(page.getByText(/海选完成/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('待人工复核').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: '查看决策路径' }).first().click();
  await expect(page.getByText('合理替代解释')).toBeVisible();
  await expect(page.getByText('建议追问')).toBeVisible();
  await expect(page.getByText('结构化决策路径')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('造假概率');
});

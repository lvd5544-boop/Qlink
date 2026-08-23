import { expect, test } from '@playwright/test';

const API = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:8000';
const PASSWORD = 'E2ePassw0rd!';

async function api(method, route, { token, body } = {}) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  let payload;
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const response = await fetch(`${API}${route}`, { method, headers, body: payload });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${route} -> ${response.status}: ${text}`);
  return text ? JSON.parse(text) : null;
}

async function sessionAsCandidate(page, login) {
  await page.goto('/login');
  await page.evaluate(
    ({ token, userId }) => {
      localStorage.setItem('token', token);
      localStorage.setItem('role', 'candidate');
      localStorage.setItem('user_id', userId);
    },
    { token: login.access_token, userId: login.user_id },
  );
}

test('C4 candidate records a sourced external outcome and sees the unified timeline', async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const email = `cand.c4.timeline.${stamp}@example.com`;

  await api('POST', '/auth/register', {
    body: { email, password: PASSWORD, role: 'candidate', terms_accepted: true, privacy_notice_acknowledged: true },
  });
  const login = await api('POST', '/auth/login', {
    body: { email, password: PASSWORD },
  });
  await sessionAsCandidate(page, login);

  await page.goto('/candidate/upload-resume');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'c4-outcome-resume.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from([
      'Name: C4 Candidate',
      `Email: ${email}`,
      'Target role: Data Analyst',
      'Skills: Python, SQL, data visualization',
      'Project: Built a dashboard and documented data-quality limitations.',
    ].join('\n')),
  });
  await expect.poll(
    async () => {
      const rows = await api('GET', `/resumes/${login.user_id}`, { token: login.access_token });
      return rows.length;
    },
    { timeout: 60_000 },
  ).toBeGreaterThan(0);
  const resumeList = await api('GET', `/resumes/${login.user_id}`, { token: login.access_token });
  expect(resumeList.length).toBeGreaterThan(0);

  const imported = await api('POST', '/advisor/target-jobs/import', {
    token: login.access_token,
    body: {
      title: `C4 External Data Analyst ${stamp}`,
      description_text: 'Data Analyst requiring Python, SQL and evidence-based communication.',
    },
  });
  await api('POST', '/applications/external-tracking', {
    token: login.access_token,
    body: { job_id: String(imported.job.id), resume_id: String(resumeList[0].id) },
  });

  await page.goto('/candidate/applied-jobs');
  await expect(page.getByText(`C4 External Data Analyst ${stamp}`)).toBeVisible();
  await page.getByRole('button', { name: '更新结果' }).click();
  await expect(page.getByText('申请结果时间线')).toBeVisible();
  await expect(page.getByText('由你记录').first()).toBeVisible();

  await page.getByRole('button', { name: '记录进入面试' }).click();
  const modal = page.getByRole('dialog', { name: '确认记录：已进入面试' });
  await expect(modal).toBeVisible();
  await modal.getByLabel('企业原始反馈（可选）').fill('Recruiter confirmed a first-round interview.');
  await modal.getByRole('button', { name: '确认记录' }).click();

  await expect(page.getByText('Recruiter confirmed a first-round interview.')).toBeVisible();
  await expect(page.getByText('已收到面试邀请').first()).toBeVisible();
  await expect(page.getByText('这次建议为什么变化')).toBeVisible();
  await expect(page.getByText('用已确认经历准备针对性面试故事')).toBeVisible();
  await expect(page.getByText('不会自动修改简历或已确认经历')).toBeVisible();
  await expect(page.getByText('未通过且没有具体反馈时，不会自动生成新的能力缺口。')).toBeVisible();
});

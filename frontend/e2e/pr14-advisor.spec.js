import { expect, test } from '@playwright/test';

const API = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:8000';
const PASSWORD = 'E2ePassw0rd!';

async function api(method, route, { token, body, headers = {} } = {}) {
  const requestHeaders = { ...headers };
  if (token) requestHeaders.Authorization = `Bearer ${token}`;
  let payload;
  if (body !== undefined) {
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

async function sessionAs(page, token, userId) {
  await page.goto('/login');
  await page.evaluate(
    ({ accessToken, candidateId }) => {
      localStorage.setItem('token', accessToken);
      localStorage.setItem('role', 'candidate');
      localStorage.setItem('user_id', candidateId);
    },
    { accessToken: token, candidateId: userId },
  );
}

test('PR14 advisor profile, readiness and cited answer', async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const email = `cand.pr14.${stamp}@example.com`;

  await api('POST', '/auth/register', {
    body: { email, password: PASSWORD, role: 'candidate' },
  });
  const login = await api('POST', '/auth/login', {
    body: { email, password: PASSWORD },
  });
  await sessionAs(page, login.access_token, login.user_id);

  await page.goto('/candidate/upload-resume');
  await page.locator('input[type="file"]').setInputFiles({
    name: 'pr14-advisor-resume.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      [
        'Name: PR14 Candidate',
        `Email: ${email}`,
        'Target role: Python backend engineer',
        'Skills: Python, SQL, FastAPI',
        'Project: Built a Python API and measured response latency.',
      ].join('\n'),
    ),
  });
  await expect
    .poll(
      async () => {
        const rows = await api('GET', `/resumes/${login.user_id}`, {
          token: login.access_token,
        });
        return Array.isArray(rows) ? rows.length : 0;
      },
      { timeout: 60_000 },
    )
    .toBeGreaterThan(0);

  const imported = await api('POST', '/advisor/target-jobs/import', {
    token: login.access_token,
    headers: { 'Idempotency-Key': `pr14-target-${stamp}` },
    body: {
      title: 'Python Backend Engineer',
      description_text: [
        'Python Backend Engineer',
        'Required skills: Python, SQL, FastAPI',
        'Responsibilities: build reliable APIs and improve service latency.',
        'Location: Shanghai',
      ].join('\n'),
    },
  });
  const jobId = String(imported.job.id);

  await page.goto(`/candidate/advisor?job_id=${jobId}`);
  await expect(
    page.getByRole('heading', { name: '目标岗位画像与 AI 求职顾问' }),
  ).toBeVisible();
  for (const heading of [
    '这个企业这个岗位明确要求什么',
    '该职业通常需要什么',
    '公司公开业务和工作语境是什么',
    '市场中出现了什么趋势',
  ]) {
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  }
  await expect(page.getByText('软件和信息技术服务人员')).toBeVisible();

  const readiness = page.getByRole('button', {
    name: '生成岗位准备度与行动建议',
  });
  await expect(readiness).toBeEnabled();
  await readiness.click();
  await expect(page.getByText('当前材料支持的准备度')).toBeVisible();
  await expect(
    page.getByText('未来行动仅为反事实情景，不会提高当前准备度'),
  ).toBeVisible();

  await page
    .getByPlaceholder('围绕这个岗位提问。顾问不会把市场趋势或公司年报说成招聘要求。')
    .fill('我应该优先准备什么？');
  await page.getByRole('button', { name: '发送' }).click();
  await expect(page.locator('.advisor-message-ai')).toBeVisible();
  await expect(page.getByText(/企业 JD/).first()).toBeVisible();
  await expect(page.getByText(/事实|推断/).first()).toBeVisible();
});

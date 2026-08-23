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
    body: { email, password: PASSWORD, role: 'candidate', terms_accepted: true, privacy_notice_acknowledged: true },
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
    page.getByRole('heading', { name: '岗位准备助手' }),
  ).toBeVisible();
  await expect(page.getByText('这个岗位最看重什么')).toBeVisible();
  await page.getByText('查看职业参考、公司背景和信息来源（可选）').click();
  await expect(page.getByText('A · 企业岗位真相源')).toBeVisible();
  await expect(page.getByText('B · 职业通用参考')).toBeVisible();
  await expect(page.getByText('C · 公司公开语境')).toBeVisible();
  await expect(page.getByText('D · 经许可市场信号')).toBeVisible();

  const readiness = page.getByRole('button', {
    name: '分析我该先做什么',
  });
  await expect(readiness).toBeEnabled();
  await readiness.click();
  await expect(page.getByText('先处理能改变这次申请的事项')).toBeVisible();
  await page.getByText('查看准备度参考（可选）').click();
  await expect(page.getByText('当前材料覆盖情况')).toBeVisible();

  await page
    .getByPlaceholder('例如：我应该先改哪一段经历？')
    .fill('我应该优先准备什么？');
  await page.getByRole('button', { name: '发送' }).click();
  await expect(page.locator('.advisor-message-ai')).toBeVisible();
  await expect(page.getByText(/企业 JD/).first()).toBeVisible();
  await expect(page.getByText(/事实|推断/).first()).toBeVisible();
});

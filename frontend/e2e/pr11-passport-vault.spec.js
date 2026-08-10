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
  const res = await fetch(`${API}${route}`, {
    method,
    headers: requestHeaders,
    body: payload,
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

test('career passport and evidence vault candidate UI', async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const email = `cand.pr11.${stamp}@example.com`;

  await api('POST', '/auth/register', {
    body: { email, password: PASSWORD, role: 'candidate' },
  });
  const login = await api('POST', '/auth/login', {
    body: { email, password: PASSWORD },
  });
  const token = login.access_token;

  await sessionAs(page, token, 'candidate', login.user_id);

  await page.goto('/candidate/career-passport');
  await expect(page.getByRole('heading', { name: '我的经历与能力' })).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: '补充一段经历' }).click();
  await page.getByLabel('经历类型').click();
  await page.getByText('项目', { exact: true }).click();
  await page.getByLabel('组织/学校').fill('PR11 E2E Org');
  await page.getByLabel('职位/项目标题').fill('PR11 E2E Role');
  await page.getByRole('button', { name: '保存到职业档案' }).click();
  await expect(page.getByRole('heading', { name: 'PR11 E2E Role' })).toBeVisible({
    timeout: 20000,
  });

  await page.goto('/candidate/evidence-vault');
  await expect(page.getByRole('heading', { name: '经历材料库（可选补充）' })).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: '添加说明、链接或文件' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('补充经历依据（可选）')).toBeVisible();
  await dialog.getByLabel('材料类型').click();
  await page.getByText('文档', { exact: true }).click();
  await dialog.getByLabel('标题').fill('PR11 E2E Evidence.txt');
  await dialog.locator('input[type="file"]').setInputFiles({
    name: 'pr11-e2e.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('PR11 safe browser upload and signed download'),
  });
  await dialog.locator('button[type="submit"]').scrollIntoViewIfNeeded();
  await dialog.locator('button[type="submit"]').click();
  await expect(page.getByText('PR11 E2E Evidence.txt').first()).toBeVisible({ timeout: 20000 });

  const downloadButton = page.getByRole('button', { name: '短时下载' }).first();
  await expect(downloadButton).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await downloadButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('PR11 E2E Evidence');
});

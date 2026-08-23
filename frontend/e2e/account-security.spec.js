import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL
  || `http://127.0.0.1:${process.env.E2E_PORT || '4173'}`;
const API_URL = new URL('/api/', BASE_URL).toString().replace(/\/$/, '');
const OLD_PASSWORD = 'QLinkSecurity9!';
const NEW_PASSWORD = 'QLinkFresh8Z!';

test('changing password signs out every existing session', async ({ page, request }) => {
  const email = `qlink.security.${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(OLD_PASSWORD);
  await page.getByRole('checkbox', { name: /隐私说明/ }).check();
  await page.getByRole('checkbox', { name: /服务条款/ }).check();
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(OLD_PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/candidate\/dashboard/);
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull();

  const secondLoginResponse = await request.post(`${API_URL}/auth/login`, {
    data: { email, password: OLD_PASSWORD },
  });
  const secondLogin = await secondLoginResponse.json();

  await page.getByRole('menuitem', { name: /更多/ }).click();
  await page.getByRole('menuitem', { name: /账号安全/ }).click();
  await expect(page.getByRole('heading', { name: '账号安全' })).toBeVisible();
  await page.getByLabel('当前密码').fill(OLD_PASSWORD);
  await page.getByLabel('新密码', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('确认新密码').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: '修改密码并退出所有设备' }).click();

  await expect(page).toHaveURL(/\/login\?reason=password_changed/);
  await expect(page.getByText('密码已修改，所有设备已退出，请重新登录')).toBeVisible();

  const staleSession = await request.get(`${API_URL}/pilot/me`, {
    headers: { Authorization: `Bearer ${secondLogin.access_token}` },
  });
  expect(staleSession.status()).toBe(401);
  const oldLogin = await request.post(`${API_URL}/auth/login`, {
    data: { email, password: OLD_PASSWORD },
  });
  expect(oldLogin.status()).toBe(401);
  const newLogin = await request.post(`${API_URL}/auth/login`, {
    data: { email, password: NEW_PASSWORD },
  });
  expect(newLogin.ok()).toBeTruthy();
});

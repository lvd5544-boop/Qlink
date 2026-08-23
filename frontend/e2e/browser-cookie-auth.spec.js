import { expect, test } from '@playwright/test';

const PASSWORD = 'QLinkBrowser9!';
const NEW_PASSWORD = 'QLinkBrowser8Z!';

test('browser session stays in HttpOnly cookie and CSRF protects writes', async ({ page, context }) => {
  const email = `qlink.browser.cookie.${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(PASSWORD);
  await page.getByRole('checkbox', { name: /隐私说明/ }).check();
  await page.getByRole('checkbox', { name: /服务条款/ }).check();
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByPlaceholder('邮箱').fill(email);
  await page.getByPlaceholder('密码').fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await expect(page).toHaveURL(/\/candidate\/dashboard/);

  const browserState = await page.evaluate(() => ({
    token: localStorage.getItem('token'),
    session: localStorage.getItem('auth_session'),
    readableCookies: document.cookie,
  }));
  expect(browserState.token).toBeNull();
  expect(browserState.session).toBe('1');
  expect(browserState.readableCookies).toContain('qlink_csrf=');
  expect(browserState.readableCookies).not.toContain('qlink_session=');

  const cookies = await context.cookies();
  const sessionCookie = cookies.find((cookie) => cookie.name === 'qlink_session');
  const csrfCookie = cookies.find((cookie) => cookie.name === 'qlink_csrf');
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(csrfCookie?.httpOnly).toBe(false);

  const wsResult = await page.evaluate(async () => {
    const userId = localStorage.getItem('user_id');
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(`ws://127.0.0.1:8000/ws/interview/${userId}?mode=profile`);
      const timer = setTimeout(() => reject(new Error('WebSocket auth timeout')), 5000);
      socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', requested_uses: {} }));
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === 'auth_ok') {
          clearTimeout(timer);
          socket.close();
          resolve('auth_ok');
          return;
        }
      };
      socket.onerror = () => {
        clearTimeout(timer);
        reject(new Error('WebSocket auth failed'));
      };
    });
  });
  expect(wsResult).toBe('auth_ok');

  await page.goto('/candidate/security');
  await page.getByLabel('当前密码').fill(PASSWORD);
  await page.getByLabel('新密码', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('确认新密码').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: '修改密码并退出所有设备' }).click();
  await expect(page).toHaveURL(/\/login\?reason=password_changed/);
  expect((await context.cookies()).some((cookie) => cookie.name === 'qlink_session')).toBe(false);
});

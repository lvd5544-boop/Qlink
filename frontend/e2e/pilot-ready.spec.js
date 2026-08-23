import { expect, test } from '@playwright/test';

const PASSWORD = 'QLinkPilotPass9!';

test('candidate controls pilot consent, feedback, withdrawal, and account deletion', async ({ page, request }) => {
  const email = `qlink.pilot.${Date.now()}@example.com`;
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
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull();

  await page.getByRole('menuitem', { name: /试用引导与反馈/ }).click();
  await expect(page).toHaveURL(/\/candidate\/pilot/);
  await expect(page.getByRole('heading', { name: /Pilot 试用与反馈/ })).toBeVisible();
  await expect(page.getByText('未参加 / Not enrolled')).toBeVisible();

  const switches = page.getByRole('switch');
  await expect(switches).toHaveCount(2);
  await expect(switches.nth(1), '模型改进授权必须默认关闭').toHaveAttribute('aria-checked', 'false');

  await page.getByRole('button', { name: '同意并开始 / Join pilot' }).click();
  await expect(page.getByText('已参加 / Enrolled')).toBeVisible();
  await expect(switches.nth(1), '加入试用不得偷偷开启模型改进').toHaveAttribute('aria-checked', 'false');

  await page.getByLabel('发生了什么？请勿填写身份证号、密码或其他敏感信息。').fill(
    'The evidence boundary and next action were clear.',
  );
  await page.getByRole('button', { name: '提交反馈' }).click();
  await expect(page.getByText('反馈已收到，谢谢你帮助我们改进')).toBeVisible();

  await page.getByRole('button', { name: '退出 pilot / Withdraw' }).click();
  await expect(page.getByText('未参加 / Not enrolled')).toBeVisible();
  await expect(page.getByRole('button', { name: '提交反馈' })).toBeDisabled();

  await page.getByRole('button', { name: '删除我的账号和数据' }).click();
  const dialog = page.getByRole('dialog', { name: '永久删除账号和数据' });
  await dialog.getByRole('textbox').fill('删除我的账号');
  await dialog.getByRole('button', { name: '确认永久删除' }).click();
  await expect(page).toHaveURL(/\/login\?reason=account_deleted/);
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible();

  const deletedLogin = await request.post('/api/auth/login', {
    data: { email, password: PASSWORD },
  });
  expect(deletedLogin.status(), '删除账号后旧凭据不得继续登录').toBe(401);
});

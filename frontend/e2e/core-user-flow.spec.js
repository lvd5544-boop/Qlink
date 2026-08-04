import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const API_URL = new URL('/api/', BASE_URL).toString().replace(/\/$/, '');
const INVITE = process.env.EMPLOYER_INVITE_CODE || 'e2e-employer-invite';
const PASSWORD = 'QLinkE2ePass9!';
const TARGET_JOB_TITLE = `QLink 核心流程后端工程师 ${Date.now()}`;

async function api(request, method, route, { token, data } = {}) {
  const response = await request.fetch(`${API_URL}${route}`, {
    method,
    data,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  const body = await response.text();
  if (!response.ok()) {
    throw new Error(`测试夹具创建失败：${method} ${route} -> ${response.status()} ${body}`);
  }
  return body ? JSON.parse(body) : null;
}

async function setSession(page, login, role) {
  await page.goto('/login');
  await page.evaluate(
    ({ token, userRole, userId }) => {
      localStorage.setItem('token', token);
      localStorage.setItem('role', userRole);
      localStorage.setItem('user_id', userId);
    },
    {
      token: login.access_token,
      userRole: role,
      userId: login.user_id,
    },
  );
}

async function registerAndLoginCandidate(page, suffix) {
  const email = `qlink.flow.${suffix}.${Date.now()}@example.com`;
  await test.step('A：进入 QLink 并创建求职者账号', async () => {
    await page.goto('/register');
    await expect(page.getByRole('heading', { name: '创建账号' }), 'A 阻塞：用户看不到 QLink 注册入口').toBeVisible();
    await page.getByPlaceholder('邮箱').fill(email);
    await page.getByPlaceholder('密码').fill(PASSWORD);
    await page.locator('form button[type="submit"]').click();
    await expect(page, 'A 阻塞：注册完成后用户没有回到登录页').toHaveURL(/\/login/);
    await page.getByPlaceholder('邮箱').fill(email);
    await page.getByPlaceholder('密码').fill(PASSWORD);
    await page.locator('form button[type="submit"]').click();
    await expect(page, 'A 阻塞：登录后用户没有进入求职者首页').toHaveURL(/\/candidate\/dashboard/);
  });
}

async function uploadResume(page, { hasTarget }) {
  await test.step('B：导入简历或填写背景', async () => {
    await page.goto('/candidate/upload-resume');
    await expect(
      page.locator('.content-card').filter({ hasText: '选择文件并上传' }),
      'B 阻塞：用户看不到导入简历页面',
    ).toBeVisible();
    const targetLine = hasTarget ? '目标岗位：后端工程师' : '职业目标：暂未确定';
    await page.locator('input[type="file"]').setInputFiles({
      name: `qlink-${hasTarget ? 'target' : 'explore'}-resume.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from([
        '姓名：QLink E2E 用户',
        targetLine,
        '技能：Python、FastAPI、PostgreSQL',
        '经历：负责订单 API，和产品团队一起改善接口稳定性。',
        '约束：只能在上海工作，每周可投入五小时学习。',
      ].join('\n')),
    });
    await expect(
      page.getByRole('heading', { name: /解析完成：现在就能修改、预览和采纳/ }),
      'B 阻塞：上传后用户看不到解析完成结果',
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText('① 修正提取结果'), 'B 阻塞：用户看不到可核对的背景信息').toBeVisible();
  });
}

async function visibleCheckpoint(page, node, locator, expectation) {
  try {
    await expect(locator).toBeVisible({ timeout: 3_000 });
    return true;
  } catch {
    const description = `${node} 阻塞：${expectation}；当前页面 ${page.url()}`;
    await test.info().attach(`flow-blocker-${node}`, {
      body: Buffer.from(description),
      contentType: 'text/plain',
    });
    await expect.soft(locator, description).toBeVisible({ timeout: 500 });
    return false;
  }
}

test.beforeAll(async ({ browser, request }) => {
  const employerEmail = `qlink.flow.employer.${Date.now()}@example.com`;
  await api(request, 'POST', '/auth/register-employer', {
    data: { email: employerEmail, password: PASSWORD, invite_code: INVITE },
  });
  const login = await api(request, 'POST', '/auth/login', {
    data: { email: employerEmail, password: PASSWORD },
  });

  const page = await browser.newPage();
  await setSession(page, login, 'employer');
  await page.goto('/employer/post-job');
  await expect(page.getByText('粘贴 JD，确认岗位和筛选重点，一次完成发布。')).toBeVisible();
  await page.getByPlaceholder('粘贴岗位描述...').fill([
    TARGET_JOB_TITLE,
    '公司：QLink E2E Company',
    '地点：上海',
    '职责：设计并交付可靠的后端 API；与产品和前端协作；处理线上故障。',
    '要求：熟练使用 Python、FastAPI、PostgreSQL；具备自动化测试经验；能说明个人贡献和量化结果。',
  ].join('\n'));
  await page.getByRole('button', { name: '提取岗位信息' }).click();
  await expect(page.getByText('岗位草稿已生成', { exact: true }), '夹具阻塞：招聘方看不到 JD 提取结果').toBeVisible({ timeout: 60_000 });
  await page.getByLabel('岗位名称').fill(TARGET_JOB_TITLE);
  await page.getByRole('button', { name: '确认要求并发布岗位' }).click();
  await expect(page.getByText('岗位已发布，筛选重点已同步到海选工作台'), '夹具阻塞：招聘方看不到岗位发布成功结果').toBeVisible({ timeout: 60_000 });
  await page.close();
});

test('有目标岗位：从简历与目标 JD 到可导出的申请包', async ({ page }) => {
  test.setTimeout(240_000);
  await registerAndLoginCandidate(page, 'target');
  await uploadResume(page, { hasTarget: true });

  await test.step('C–G：选择目标 JD，并看到 5–8 项关键要求', async () => {
    await page.goto('/candidate/browse-jobs');
    await expect(
      page.locator('.content-card').filter({ hasText: '岗位发现与选择' }),
      'C/D 阻塞：用户看不到可选择的目标岗位',
    ).toBeVisible();
    await page.getByPlaceholder('关键字搜索').fill(TARGET_JOB_TITLE);
    await page.getByRole('button', { name: '搜索' }).click();
    const targetRow = page.getByText(TARGET_JOB_TITLE).first();
    const targetVisible = await visibleCheckpoint(page, 'D', targetRow, '用户选择“已有目标岗位”后应能选中目标 JD');
    if (!targetVisible) return;
    const row = targetRow.locator('xpath=ancestor::*[contains(@class,"ant-list-item")]');
    await row.getByRole('button', { name: '查看岗位画像' }).click();
    await expect(page.getByRole('heading', { name: '岗位准备助手' }), 'D 阻塞：选中 JD 后没有进入岗位准备流程').toBeVisible();
    const requirements = page.locator('.content-card').filter({ hasText: '这个岗位最看重什么' }).locator('.ant-list-item');
    await expect(requirements, 'G 阻塞：用户看不到从 JD 提取的关键岗位要求').toHaveCount(6, { timeout: 30_000 });
  });

  await test.step('H–P：映射经历证据并展示准备状态', async () => {
    const analyze = page.getByRole('button', { name: '分析我该先做什么' });
    if (!(await visibleCheckpoint(page, 'H', analyze, '用户看不到“将岗位要求映射到个人经历”的操作'))) return;
    await analyze.click();
    await expect(page.getByText('为你排序的下一步'), 'H/I 阻塞：分析后用户看不到证据映射或准备建议').toBeVisible({ timeout: 60_000 });
    await visibleCheckpoint(page, 'J', page.getByText(/已有证据.*直接使用/), '准备情况中没有明确展示可直接使用的已有证据');
    await visibleCheckpoint(page, 'K', page.getByText(/信息不完整.*追问/), '准备情况中没有明确展示需要立即追问的信息');
    await visibleCheckpoint(page, 'L', page.getByText(/暂未具备.*发展任务/), '准备情况中没有明确展示发展任务');
    await visibleCheckpoint(page, 'M', page.getByText(/现实约束/), '准备情况中没有单独展示现实约束');
    await visibleCheckpoint(page, 'N', page.getByText(/无法判断.*补充信息/), '准备情况中没有明确请求无法判断项的补充信息');
    await visibleCheckpoint(page, 'O', page.getByText(/最多 3 个问题/), '用户看不到最多三个补充问题及回答入口');
    await visibleCheckpoint(page, 'P', page.getByText(/更新.*证据.*准备状态/), '回答后用户看不到证据和准备状态更新结果');
  });

  await test.step('Q–T：生成、导出申请包并记录结果', async () => {
    await visibleCheckpoint(page, 'Q', page.getByText(/当前可用申请包/), '用户看不到基于当前证据生成的申请包');
    await visibleCheckpoint(page, 'R', page.getByText(/简历要点.*求职信.*面试故事/), '用户看不到简历要点、求职信素材和面试故事的导出结果');
    await visibleCheckpoint(page, 'T', page.getByText(/记录.*投递.*面试.*录用结果/), '用户看不到记录投递、面试或录用结果的入口');
  });
});

test('无目标岗位：查看当前、相邻、挑战三个方向后进入同一准备流程', async ({ page }) => {
  test.setTimeout(180_000);
  await registerAndLoginCandidate(page, 'explore');
  await uploadResume(page, { hasTarget: false });

  await test.step('C–F：无目标岗位时展示并选择三个方向', async () => {
    await page.goto('/candidate/jobs');
    await expect(
      page.locator('.content-card').filter({ hasText: '推荐岗位' }),
      'C/E 阻塞：无目标用户看不到方向探索页',
    ).toBeVisible();
    const current = await visibleCheckpoint(page, 'E-current', page.getByText(/^当前方向$/), '用户看不到“当前”方向');
    const adjacent = await visibleCheckpoint(page, 'E-adjacent', page.getByText(/^相邻方向$/), '用户看不到“相邻”方向');
    const challenge = await visibleCheckpoint(page, 'E-challenge', page.getByText(/^挑战方向$/), '用户看不到“挑战”方向');
    if (!current || !adjacent || !challenge) return;
    await visibleCheckpoint(page, 'F', page.getByRole('button', { name: /选择.*方向|选择.*岗位/ }).first(), '用户看不到选择方向或示例岗位的操作');
  });

  await test.step('G–T：选择方向后应汇入岗位要求、准备情况和申请包', async () => {
    await visibleCheckpoint(page, 'G', page.getByText(/5.?8 项关键岗位要求/), '方向选择后没有展示 5–8 项关键岗位要求');
    await visibleCheckpoint(page, 'I', page.getByText(/岗位准备情况/), '方向选择后没有展示岗位准备情况');
    await visibleCheckpoint(page, 'Q', page.getByText(/当前可用申请包/), '方向分支没有汇入当前可用申请包');
    await visibleCheckpoint(page, 'R', page.getByText(/简历要点.*求职信.*面试故事/), '方向分支没有可见的申请材料导出结果');
  });
});

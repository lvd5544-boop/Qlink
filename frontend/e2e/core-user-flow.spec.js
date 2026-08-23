import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL
  || `http://127.0.0.1:${process.env.E2E_PORT || '4173'}`;
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
    await page.getByRole('checkbox', { name: /隐私说明/ }).check();
    await page.getByRole('checkbox', { name: /服务条款/ }).check();
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
    await expect(locator).toBeVisible({ timeout: 8_000 });
  } catch (error) {
    const description = `${node} 阻塞：${expectation}；当前页面 ${page.url()}`;
    await test.info().attach(`flow-blocker-${node}`, {
      body: Buffer.from(`${description}\n\n${(await page.locator('body').innerText()).slice(0, 12_000)}`),
      contentType: 'text/plain',
    });
    throw new Error(`${description}\n${error.message}`);
  }
}

async function analyzeVisibleReadiness(page) {
  const analyze = page.getByRole('button', { name: '分析我该先做什么' });
  await visibleCheckpoint(page, 'H', analyze, '用户看不到“将岗位要求映射到个人经历”的操作');
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === 'POST'
      && response.url().includes('/advisor/jobs/')
      && response.url().endsWith('/diagnostics'),
    { timeout: 60_000 },
  );
  await analyze.click();
  const response = await responsePromise;
  expect(response.ok(), `H 阻塞：岗位要求与经历映射接口返回 ${response.status()}`).toBeTruthy();
  await visibleCheckpoint(
    page,
    'I',
    page.getByText('先处理能改变这次申请的事项'),
    '分析完成后用户看不到岗位准备情况',
  );

  const statusChecks = [
    ['J', 'readiness-ready', '已有证据：可以直接使用'],
    ['K', 'readiness-clarify', '信息不完整：需要立即追问'],
    ['L', 'readiness-develop', '暂未具备：生成发展任务'],
    ['M', 'readiness-constraint', '现实约束：单独确认'],
    ['N', 'readiness-unknown', '无法判断：请求补充信息'],
  ];
  for (const [node, testId, label] of statusChecks) {
    await visibleCheckpoint(page, node, page.getByTestId(testId).getByText(label), `准备情况中没有展示“${label}”`);
  }
  await visibleCheckpoint(
    page,
    'O',
    page.getByTestId('readiness-clarify').getByRole('button', { name: '回答并补充这条经历或证据' }).first(),
    '信息不完整时用户看不到补充问题的回答入口（页面最多展示 3 项）',
  );
  await visibleCheckpoint(
    page,
    'P',
    page.getByText('补充后重新分析会更新证据和准备状态。').first(),
    '用户看不到补充信息后如何更新准备状态',
  );
}

async function generateVisibleOpportunityPreparation(page) {
  await visibleCheckpoint(
    page,
    'T',
    page.getByRole('button', { name: '查看投递、面试和录用结果' }),
    '用户看不到记录和查看投递结果的入口',
  );
  await page.getByRole('button', { name: '生成当前可投版本并安排提升行动' }).click();
  await expect(page, 'Q 阻塞：用户没有进入申请材料工作台').toHaveURL(/\/candidate\/my-resumes/);
  const generate = page.getByTestId('pr13-generate-diagnostic');
  await visibleCheckpoint(page, 'Q', generate, '用户看不到生成当前申请包所需的岗位诊断操作');
  // click() auto-scrolls and re-resolves the locator if React replaces the
  // button while opportunity data is still loading. A separate scroll action
  // retained a detached DOM node and made both browser workflows flaky.
  await generate.click();
  await visibleCheckpoint(page, 'Q', page.getByText('本次机会准备卡'), '用户看不到基于当前证据生成的机会准备卡');
  await page.getByRole('button', { name: '生成机会准备卡' }).click();
  for (const section of ['现在可用', '面试故事', '待说清', '一个行动', '未解决要求']) {
    await visibleCheckpoint(page, 'R', page.getByText(new RegExp(section)).first(), `机会准备卡缺少“${section}”栏目`);
  }
  const downloadButton = page.getByRole('button', { name: '下载 TXT（次要）' });
  await expect(downloadButton, 'R 阻塞：用户看不到机会准备卡的次要导出操作').toBeEnabled();
  const downloadPromise = page.waitForEvent('download');
  await downloadButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename(), 'R 阻塞：导出的机会准备卡不是 TXT 文件').toMatch(/机会准备卡\.txt$/);
  await page.getByRole('button', { name: '用这批真实素材开始针对性面试' }).click();
  await expect(page, 'S 阻塞：机会准备卡没有带入结构化面试').toHaveURL(
    /\/candidate\/interview\?.*mode=target_gap.*resumeId=.*jobId=/,
  );
}

test.beforeAll(async ({ browser, request }) => {
  const employerEmail = `qlink.flow.employer.${Date.now()}@example.com`;
  await api(request, 'POST', '/auth/register-employer', {
    data: { email: employerEmail, password: PASSWORD, invite_code: INVITE, terms_accepted: true, privacy_notice_acknowledged: true },
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

test('有目标岗位：从简历与目标 JD 到机会准备卡和面试', async ({ page }) => {
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
    await visibleCheckpoint(page, 'D', targetRow, '用户选择“已有目标岗位”后应能选中目标 JD');
    const row = targetRow.locator('xpath=ancestor::*[contains(@class,"ant-list-item")]');
    await row.getByRole('button', { name: '查看岗位画像' }).click();
    await expect(page.getByRole('heading', { name: '岗位准备助手' }), 'D 阻塞：选中 JD 后没有进入岗位准备流程').toBeVisible();
    const requirements = page.locator('.content-card').filter({ hasText: '这个岗位最看重什么' }).locator('.ant-list-item');
    await expect(requirements, 'G 阻塞：用户看不到从 JD 提取的关键岗位要求').toHaveCount(6, { timeout: 30_000 });
  });

  await test.step('H–P：映射经历证据并展示准备状态', async () => {
    await analyzeVisibleReadiness(page);
  });

  await test.step('Q–T：生成、导出申请包并记录结果', async () => {
    await generateVisibleOpportunityPreparation(page);
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
    await visibleCheckpoint(page, 'E-current', page.getByTestId('career-direction-current').getByText('当前方向'), '用户看不到“当前”方向');
    await visibleCheckpoint(page, 'E-adjacent', page.getByTestId('career-direction-adjacent').getByText('相邻方向'), '用户看不到“相邻”方向');
    await visibleCheckpoint(page, 'E-challenge', page.getByTestId('career-direction-challenge').getByText('挑战方向'), '用户看不到“挑战”方向');
    const selectExample = page.getByRole('button', { name: '选择这个示例岗位' }).first();
    await visibleCheckpoint(page, 'F', selectExample, '用户看不到选择方向或示例岗位的操作');
    await selectExample.click();
    await expect(page, 'F 阻塞：选择示例岗位后没有进入统一准备流程').toHaveURL(/\/candidate\/advisor\?job_id=/);
  });

  await test.step('G–T：选择方向后应汇入岗位要求、准备情况和申请包', async () => {
    const requirements = page.locator('.content-card').filter({ hasText: '这个岗位最看重什么' }).locator('.ant-list-item');
    await expect(requirements, 'G 阻塞：方向选择后没有展示 5–8 项关键岗位要求').toHaveCount(6, { timeout: 30_000 });
    await analyzeVisibleReadiness(page);
    await generateVisibleOpportunityPreparation(page);
  });
});

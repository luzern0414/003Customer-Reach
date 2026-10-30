import { expect, test, type Page } from '@playwright/test'

const USER = process.env.E2E_USER || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin'

async function login(page: Page) {
  const response = await page.request.post('/api/auth/login', { data: { username: USER, password: PASSWORD } })
  expect(response.ok()).toBe(true)
  await page.goto('/workbench')
  await expect(page.locator('.side .brand')).toBeVisible()
}

test.beforeEach(async ({ page }) => { await login(page) })

test('登录后进入工作台，概览不重复页面标题', async ({ page }) => {
  await expect(page).toHaveURL(/\/workbench/)
  await page.goto('/')
  await expect(page.locator('.menu-item.on')).toHaveText(/概览/)
  await expect(page.locator('.kpis .kpi')).not.toHaveCount(0)
  await expect(page.locator('.page-title', { hasText: '概览' })).toHaveCount(0)
})

test('全局侧栏把会话历史放在系统设置下方', async ({ page }) => {
  await page.goto('/workbench')
  const side = page.locator('.side')
  await expect(side).toContainText('系统设置')
  await expect(side).toContainText('会话历史')
  const text = await side.innerText()
  expect(text.indexOf('系统设置')).toBeLessThan(text.indexOf('会话历史'))
  await expect(page.locator('.wb .convs')).toHaveCount(0)
})

test('执行中仍可补充条件', async ({ page }) => {
  const list = await (await page.request.get('/api/conversations')).json()
  const active = list.find((item: { status: string }) => ['queued', 'running', 'replanning'].includes(item.status))
  test.skip(!active, '本机没有执行中的任务')
  await page.goto(`/c/${active.id}`)
  await expect(page.locator('textarea')).toBeEnabled()
  await expect(page.locator('button[title="补充条件"]')).toBeEnabled()
})

test('研究报告表格在对话区全宽展示全部列', async ({ page }) => {
  const list = await (await page.request.get('/api/conversations')).json()
  let target = ''
  for (const item of list) {
    const detail = await (await page.request.get(`/api/conversations/${item.id}`)).json()
    if (detail.jobs.some((j: { mode: string; status: string }) => j.mode === 'find_buyers' && ['completed', 'partial'].includes(j.status))) { target = item.id; break }
  }
  test.skip(!target, '本机还没有完成的找买家研究')
  await page.goto(`/c/${target}`)
  const table = page.locator('.report table.grid.buyers').last()
  await expect(table).toBeVisible({ timeout: 20_000 })
  for (const head of ['采购单位', '采购标的', '预算（万元）', '发布', '投标截止', '联系人', '原文']) {
    await expect(table.locator('th', { hasText: head })).toHaveCount(1)
  }
  const fits = await page.locator('.report').last().evaluate((el) => el.scrollWidth <= el.clientWidth + 1)
  expect(fits).toBe(true)
  await table.locator('th', { hasText: '预算（万元）' }).click()
  await expect(table.locator('th.sortable.on')).toHaveCount(1)
})

test('报告日期列保持完整宽度', async ({ page }) => {
  await page.goto('/workbench')
  const dateCell = page.locator('.report .c-day').first()
  if (await dateCell.count()) await expect(dateCell).toHaveCSS('min-width', '120px')
})

test('移动端报告表格可横向滚动', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/workbench')
  const report = page.locator('.report').first()
  if (await report.count()) {
    const table = report.locator('.table-scroll').first()
    if (await table.count()) expect(await table.evaluate((el) => el.scrollWidth >= el.clientWidth)).toBe(true)
  }
})

test('线索默认只看可投标，可切换并修改状态', async ({ page }) => {
  await page.goto('/leads')
  await expect(page).toHaveURL(/open=1/)
  const rows = page.locator('.el-table__body tr')
  await expect(page.locator('.open-only .el-switch')).toHaveClass(/is-checked/)
  await page.locator('.open-only .el-switch').click()
  await expect(page).toHaveURL(/open=0/)
  await page.locator('.chip', { hasText: '全部' }).click()
  await expect(rows.first()).toBeVisible()
  // 改第一条线索的状态，再按接口改回原状态
  const href = await rows.first().locator('a.cell-main').getAttribute('href')
  const id = href!.split('/').pop()!
  const before = (await (await page.request.get(`/api/leads/${id}`)).json()).status
  const next = before === 'contacted' ? 'following' : 'contacted'
  const label = next === 'contacted' ? '已联系' : '持续跟进'
  await rows.first().locator('.status-select').click()
  await page.locator('.el-select-dropdown__item:visible', { hasText: label }).click()
  await expect(page.locator('.el-message--success')).toBeVisible()
  expect((await (await page.request.get(`/api/leads/${id}`)).json()).status).toBe(next)
  const restored = await page.request.patch(`/api/leads/${id}`, { data: { status: before } })
  expect(restored.ok()).toBe(true)
})

test('企业档案列表单行展示并可分页', async ({ page }) => {
  await page.goto('/companies')
  await expect(page.locator('.el-table__body tr').first()).toBeVisible()
  await expect(page.locator('.page-title', { hasText: '企业档案' })).toHaveCount(0)
  await expect(page.locator('.el-pagination')).toBeVisible()
  const height = await page.locator('.el-table__body tr').first().evaluate((el) => el.getBoundingClientRect().height)
  expect(height).toBeLessThanOrEqual(46)
})

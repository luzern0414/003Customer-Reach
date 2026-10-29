import { defineConfig } from '@playwright/test'

// 端到端测试：用本机 Edge 打开已启动的 DealRadar（默认 http://127.0.0.1:8000），只读为主，改动的数据在用例结束前改回。
export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 60_000,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8000',
    channel: 'msedge',
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
  },
})

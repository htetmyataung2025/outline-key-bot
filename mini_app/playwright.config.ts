import { defineConfig } from '@playwright/test'

const baseURL = process.env.TEST_BASE_URL ?? 'http://127.0.0.1:4174'
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  workers: 2,
  timeout: 30_000,
  expect: { timeout: 5000 },
  reporter: [['list']],
  use: { baseURL, browserName: 'chromium', viewport: { width: 390, height: 844 }, hasTouch: true, trace: 'retain-on-failure' },
  webServer: process.env.TEST_BASE_URL ? undefined : {
    command: 'npm run dev -- --port 4174', url: baseURL, reuseExistingServer: !process.env.CI, timeout: 30_000,
  },
})

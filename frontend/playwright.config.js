import { defineConfig } from '@playwright/test';

const realApi = process.env.RURIS_REAL_API === '1';
const url = `http://127.0.0.1:${realApi ? 5174 : 5173}`;

export default defineConfig({
  testDir: './tests',
  timeout: 20000,
  workers: 1,
  globalTeardown: './tests/stop-real-server.js',
  use: {
    baseURL: url,
    channel: process.platform === 'win32' ? 'msedge' : undefined,
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url,
    reuseExistingServer: !realApi && !process.env.CI,
  },
});

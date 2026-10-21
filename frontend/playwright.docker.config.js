import { defineConfig } from '@playwright/test';

const target = new URL(process.env.RURIS_DOCKER_URL || 'http://127.0.0.1:18080');
if (process.env.RURIS_DOCKER_SMOKE !== '1' || target.hostname !== '127.0.0.1' || target.protocol !== 'http:' || Number(target.port) < 18000) {
  throw new Error('Set RURIS_DOCKER_SMOKE=1 and an isolated loopback URL on port 18000 or higher.');
}

export default defineConfig({
  testDir: './tests',
  testMatch: ['real-flows.spec.js', 'docker-restore.spec.js'],
  workers: 1,
  timeout: 120000,
  use: { baseURL: target.origin, channel: process.platform === 'win32' ? 'msedge' : undefined,
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure' },
});

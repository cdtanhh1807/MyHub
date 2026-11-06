import { defineConfig } from '@playwright/test';

// Dùng Edge đã cài sẵn; không tải browser và không tự khởi động backend/MongoDB.
export default defineConfig({
  testDir: './tests', outputDir: '../data/test-results', fullyParallel: false, workers: 1,
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173', channel: 'msedge', headless: true, trace: 'retain-on-failure' },
  reporter: 'list', timeout: 30000,
});

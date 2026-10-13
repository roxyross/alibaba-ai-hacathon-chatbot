import process from 'node:process';
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL ?? process.env.BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    {
      name: 'desktop-hd',
      use: {
        viewport: { width: 1920, height: 1080 },
      },
    },
    {
      name: 'desktop-standard',
      use: {
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'tablet-landscape',
      use: {
        viewport: { width: 1024, height: 768 },
      },
    },
    {
      name: 'tablet-portrait',
      use: {
        viewport: { width: 768, height: 1024 },
      },
    },
    {
      name: 'mobile-ios',
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'mobile-android',
      use: {
        viewport: { width: 360, height: 800 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'mobile-compact',
      use: {
        viewport: { width: 320, height: 568 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});

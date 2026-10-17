import { test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const SCREENSHOT_DIR = path.resolve(process.cwd(), '../docs/screenshots/redesign');

test.describe('Redesign Screenshot Capture', () => {
  test.beforeAll(() => {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
      fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
  });

  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/sessions**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'sess_default_1',
            title: 'Welcome to Roxy AI Workspace',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            session_type: 'chat',
            pinned: true,
            archived: false,
          },
          {
            id: 'sess_default_2',
            title: 'Full-Stack SaaS Development',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            session_type: 'task',
            pinned: false,
            archived: false,
          },
        ]),
      });
    });

    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_test_1',
          email: 'developer@roxy.ai',
          is_active: true,
        }),
      });
    });

    await page.route('**/api/v1/reminders/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/devices/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'dev_host_1',
            device_name: 'Primary Workstation',
            os_platform: 'windows',
            is_current_host: true,
            status: 'online',
          },
        ]),
      });
    });

    await page.route('**/api/v1/settings/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });

    await page.route('**/api/v1/ai/providers/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: [
            { provider: 'gemini', status: 'healthy', default: true },
            { provider: 'groq', status: 'healthy' },
            { provider: 'grok', status: 'healthy' },
          ],
        }),
      });
    });

    await page.route('**/api/v1/models**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: [
            {
              name: 'gemini',
              display_name: 'Google Gemini',
              enabled: true,
              models: [
                { name: 'gemini-4-argon', display_name: 'Gemini 4 Argon (Default)', enabled: true, task_types: ['general'], max_tokens: 32768 },
              ],
            },
          ],
        }),
      });
    });

    await page.addInitScript(() => {
      const fakeJwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfdGVzdF8xIiwiZW1haWwiOiJkZXZlbG9wZXJAcm94eS5haSIsImV4cCI6MTk5OTk5OTk5OX0.dummy_sig';
      localStorage.setItem('roxy.access_token', fakeJwt);
      localStorage.setItem('roxy_guest_prompt_count', '0');
    });
  });

  test('capture redesigned desktop, tablet, and mobile views', async ({ page }) => {
    // 1. Desktop Light (1440x900)
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-redesign-desktop-1440-chat-light.png') });

    // 2. Desktop Dark (1440x900)
    const themeBtn = page.locator('.theme-toggle-btn');
    if (await themeBtn.isVisible()) {
      await themeBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-redesign-desktop-1440-chat-dark.png') });
      await themeBtn.click(); // toggle back to light
      await page.waitForTimeout(500);
    }

    // 3. Tablet Portrait (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-redesign-tablet-768-chat.png') });

    // 4. Mobile iPhone (375x812)
    await page.setViewportSize({ width: 375, height: 812 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-redesign-mobile-375-chat.png') });

    // 5. Desktop New Task Modal
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const newTaskBtn = page.locator('.app__header-quick-action--task, .session-sidebar__new-task-btn').first();
    if (await newTaskBtn.isVisible()) {
      await newTaskBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-redesign-desktop-1440-new-task-modal.png') });
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
    }

    // 6. Code Studio / IDE
    await page.goto('/code-studio');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-redesign-desktop-1440-code-studio.png') });

    // 7. Cowork Workspace
    await page.goto('/');
    const coworkBtn = page.locator('.app__header-quick-action--cowork');
    if (await coworkBtn.isVisible()) {
      await coworkBtn.click();
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-redesign-desktop-1440-cowork.png') });
      await coworkBtn.click(); // exit cowork
      await page.waitForTimeout(300);
    }

    // 8. Collapsed Sidebar Rail
    const collapseBtn = page.locator('.session-sidebar__collapse-btn');
    if (await collapseBtn.isVisible()) {
      await collapseBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08-redesign-desktop-1440-collapsed-rail.png') });
    }
  });
});

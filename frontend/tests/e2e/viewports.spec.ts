import { test, expect } from '@playwright/test';

// Required 11-viewport matrix per Section 4 specifications
const REQUIRED_VIEWPORTS = [
  { name: 'mobile-compact-320', width: 320, height: 568, isTouch: true },
  { name: 'mobile-android-360', width: 360, height: 800, isTouch: true },
  { name: 'mobile-iphone-375', width: 375, height: 812, isTouch: true },
  { name: 'mobile-iphone-pro-390', width: 390, height: 844, isTouch: true },
  { name: 'mobile-iphone-max-430', width: 430, height: 932, isTouch: true },
  { name: 'tablet-portrait-768', width: 768, height: 1024, isTouch: true },
  { name: 'tablet-landscape-1024', width: 1024, height: 768, isTouch: false },
  { name: 'laptop-small-1280', width: 1280, height: 800, isTouch: false },
  { name: 'laptop-common-1366', width: 1366, height: 768, isTouch: false },
  { name: 'desktop-standard-1440', width: 1440, height: 900, isTouch: false },
  { name: 'desktop-hd-1920', width: 1920, height: 1080, isTouch: false },
];

test.describe('Responsive Viewport Matrix Audit (11 Viewports)', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API routes with deterministic test fixtures
    await page.route('**/api/v1/sessions**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'sess_default_1',
            title: 'Welcome to Roxy AI',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            session_type: 'chat',
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

    await page.route('**/api/v1/reminders*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/devices*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/settings*', async (route) => {
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
                { name: 'gemini-3.8-flash', display_name: 'Gemini 3.8 Flash', enabled: true, task_types: ['general', 'audio'], max_tokens: 8192 },
              ],
            },
            {
              name: 'grok',
              display_name: 'xAI Grok',
              enabled: true,
              models: [
                { name: 'grok-4.7', display_name: 'xAI Grok 4.7', enabled: true, task_types: ['general'], max_tokens: 16384 },
              ],
            },
            {
              name: 'groq',
              display_name: 'Groq',
              enabled: true,
              models: [
                { name: 'qwen/qwen3.8-27b', display_name: 'Groq Qwen 27B', enabled: true, task_types: ['general'], max_tokens: 4096 },
              ],
            },
          ],
        }),
      });
    });

    // Provide authenticated token and guest state
    await page.addInitScript(() => {
      const fakeJwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfdGVzdF8xIiwiZW1haWwiOiJkZXZlbG9wZXJAcm94eS5haSIsImV4cCI6MTk5OTk5OTk5OX0.dummy_sig';
      localStorage.setItem('roxy.access_token', fakeJwt);
      localStorage.setItem('roxy_guest_prompt_count', '0');
    });
  });

  for (const vp of REQUIRED_VIEWPORTS) {
    test(`renders cleanly without horizontal overflow on ${vp.name} (${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      // Track console errors
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });

      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Verify root element renders
      const root = page.locator('#root');
      await expect(root).toBeVisible();

      // Check document horizontal overflow: scrollWidth must not exceed clientWidth (+1px tolerance)
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

      // Verify primary header container fits within viewport
      const header = page.locator('.app__header');
      if (await header.isVisible()) {
        const headerBox = await header.boundingBox();
        if (headerBox) {
          expect(headerBox.width).toBeLessThanOrEqual(vp.width + 1);
        }
      }

      // Verify chat input or send container is reachable
      const chatInput = page.locator('textarea, input[placeholder*="message"]').first();
      await expect(chatInput).toBeVisible({ timeout: 5000 });

      // Verify touch targets on touch devices
      if (vp.isTouch) {
        const buttons = page.locator('.app__header button:visible, .chat-input button:visible');
        const count = await buttons.count();
        for (let i = 0; i < Math.min(count, 5); i++) {
          const btn = buttons.nth(i);
          const box = await btn.boundingBox();
          if (box && box.width > 0 && box.height > 0) {
            // Interactive button width and height should have sufficient touch target
            expect(box.width >= 24 && box.height >= 24).toBeTruthy();
          }
        }
      }

      // Save screenshot artifact for CI report
      await page.screenshot({ path: `tests/e2e/screenshots/viewport-${vp.name}.png` });
    });

    test(`modal overlays render within bounds on ${vp.name} (${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // 1. Open New Task modal via header action
      const taskBtn = page.locator('.app__header .app__header-quick-action--task, .app__header button[aria-label*="New Task"]').first();
      if (await taskBtn.isVisible()) {
        await taskBtn.click();
        const taskModal = page.locator('.new-task-modal__window');
        await expect(taskModal).toBeVisible({ timeout: 5000 });
        const modalBox = await taskModal.boundingBox();
        if (modalBox) {
          expect(modalBox.width).toBeLessThanOrEqual(vp.width + 1);
        }
        // Close modal
        await page.keyboard.press('Escape');
        await expect(page.locator('.new-task-modal__backdrop')).toHaveCount(0, { timeout: 5000 });
      }

      // 2. Open Settings modal via header action
      const settingsBtn = page.locator('.app__header .app__settings-btn, .app__header button[aria-label*="Settings"]').first();
      if (await settingsBtn.isVisible()) {
        await settingsBtn.click();
        const settingsModal = page.locator('.settings-card');
        await expect(settingsModal).toBeVisible({ timeout: 5000 });
        const modalBox = await settingsModal.boundingBox();
        if (modalBox) {
          expect(modalBox.width).toBeLessThanOrEqual(vp.width + 1);
        }
        // Close settings modal
        const closeSettingsBtn = page.locator('.settings-close-btn');
        if (await closeSettingsBtn.isVisible()) {
          await closeSettingsBtn.click();
        } else {
          await page.locator('.settings-overlay').click({ position: { x: 5, y: 5 }, force: true });
        }
        await expect(page.locator('.settings-overlay')).toHaveCount(0, { timeout: 5000 });
      }
    });
  }
});

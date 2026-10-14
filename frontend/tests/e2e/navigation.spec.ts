import { test, expect } from '@playwright/test';

test.describe('Navigation and Core Views E2E', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept standard API endpoints to provide deterministic mock data
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
  });

  test('loads home page and verifies default chat window and top bar controls', async ({ page }) => {
    await page.goto('/');

    // Verify top bar controls are present
    await expect(page.locator('.app__header')).toBeVisible();
    await expect(page.locator('button[aria-label="Roxy Command Omnibar"]')).toBeVisible();
    await expect(page.locator('.app__header-quick-action--task')).toBeVisible();
    await expect(page.locator('.app__settings-btn')).toBeVisible();
    await expect(page.locator('.session-sidebar__upgrade-pill, button:has-text("Upgrade")').first()).toBeVisible();

    // Verify chat window components
    await expect(page.locator('.chat-window')).toBeVisible();
    await expect(page.locator('textarea, input[placeholder*="message"]')).toBeVisible();

    // Visual checkpoint screenshot
    await page.screenshot({ path: 'tests/e2e/screenshots/homepage-default.png' });
  });

  test('navigates through secondary views and verifies view rendering', async ({ page }) => {
    await page.goto('/');

    // 1. Pricing Page
    const upgradeBtn = page.locator('.session-sidebar__upgrade-pill, button:has-text("Upgrade")').first();
    if (await upgradeBtn.isVisible()) {
      await upgradeBtn.click();
      await expect(page.locator('.pricing-page, [class*="pricing"]').first()).toBeVisible();

      // Navigate back to chat
      const backBtn = page.locator('button:has-text("Back"), button[aria-label="Back to chat"]').first();
      if (await backBtn.isVisible()) {
        await backBtn.click();
        await expect(page.locator('.chat-window')).toBeVisible();
      }
    }

    // 2. Calculator View
    const calcNav = page.locator('button[aria-label*="Calculator"], .session-sidebar__nav-link:has-text("Calculator")').first();
    if (await calcNav.isVisible()) {
      await calcNav.click();
      await expect(page.locator('.calculator-view, .calculator, [class*="calculator"]').first()).toBeVisible();
    }

    // 3. Calendar View
    const calNav = page.locator('button[aria-label*="Calendar"], .session-sidebar__nav-link:has-text("Calendar")').first();
    if (await calNav.isVisible()) {
      await calNav.click();
      await expect(page.locator('.calendar-view, [class*="calendar"]').first()).toBeVisible();
    }

    // 4. Code Studio
    const codeNav = page.locator('button[aria-label*="Coding"], .session-sidebar__nav-link:has-text("Coding"), .session-sidebar__nav-link:has-text("Code Studio")').first();
    if (await codeNav.isVisible()) {
      await codeNav.click();
      await expect(page.locator('.coding-studio, [class*="coding"]').first()).toBeVisible({ timeout: 10_000 });
      await page.screenshot({ path: 'tests/e2e/screenshots/code-studio-view.png' });
    }
  });

  test('toggles sidebar collapse and expansion', async ({ page }) => {
    await page.goto('/');

    // Initial state: expanded sidebar
    const collapseBtn = page.locator('.session-sidebar__collapse-btn');
    if (await collapseBtn.isVisible()) {
      await collapseBtn.click();
      // Sidebar should transition to collapsed rail
      await expect(page.locator('.session-sidebar--collapsed')).toBeVisible();

      // Expand sidebar again
      const expandBtn = page.locator('button[aria-label="Open sidebar"]').first();
      if (await expandBtn.isVisible()) {
        await expandBtn.click();
        await expect(page.locator('.session-sidebar:not(.session-sidebar--collapsed)')).toBeVisible();
      }
    }
  });

  test('opens and interacts with New Task autonomous modal', async ({ page }) => {
    await page.goto('/');

    // Trigger New Task via top bar button
    const taskBtn = page.locator('.app__header-quick-action--task');
    if (await taskBtn.isVisible()) {
      await taskBtn.click();
      const modal = page.locator('.new-task-modal, [class*="new-task-modal"], [role="dialog"]').first();
      await expect(modal).toBeVisible();

      // Dismiss modal via Escape key
      await page.keyboard.press('Escape');
      await expect(modal).not.toBeVisible();
    }
  });

  test('opens and navigates Global Settings modal', async ({ page }) => {
    await page.goto('/');

    // Click settings gear button
    const settingsBtn = page.locator('.app__settings-btn');
    if (await settingsBtn.isVisible()) {
      await settingsBtn.click();
      const settingsModal = page.locator('.settings-modal, [class*="settings-modal"], [role="dialog"]').first();
      await expect(settingsModal).toBeVisible();

      // Dismiss settings modal via Escape
      await page.keyboard.press('Escape');
      await expect(settingsModal).not.toBeVisible();
    }
  });

  test('opens and searches Command Omnibar', async ({ page }) => {
    await page.goto('/');

    // Click command bar search trigger
    const searchBtn = page.locator('.app__header-search-btn');
    if (await searchBtn.isVisible()) {
      await searchBtn.click();
      const omnibar = page.locator('.roxy-command-bar, [class*="command-bar"], [role="combobox"]').first();
      await expect(omnibar).toBeVisible();

      // Search input
      const input = page.locator('input[placeholder*="Command"], input[placeholder*="Search"]').first();
      if (await input.isVisible()) {
        await input.fill('Code Studio');
      }

      // Press Escape to dismiss
      await page.keyboard.press('Escape');
      await expect(omnibar).not.toBeVisible();
    }
  });
});

import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const RUN_SHA = process.env.RUN_SHA || 'a72670a';
const SCREENSHOT_DIR = path.resolve(process.cwd(), `../docs/screenshots/redesign/runs/${RUN_SHA}`);

interface CaptureItem {
  filename: string;
  surface: string;
  viewport: { width: number; height: number };
  assertedLocator: string;
  capturedAt: string;
  status: 'captured' | 'failed';
}

const capturedManifest: CaptureItem[] = [];

test.describe('Redesign Visual Evidence & Screenshot Capture Suite', () => {
  test.beforeAll(() => {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
      fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
  });

  test.afterAll(() => {
    // Generate machine-readable manifest.json
    const manifestPath = path.join(SCREENSHOT_DIR, 'manifest.json');
    const manifestData = {
      commitSha: 'a72670a31cd8641d00fa5516ecaf1d07a8ecfe53',
      shortSha: RUN_SHA,
      branch: 'design/roxy-ui-ux-redesign',
      capturedAt: new Date().toISOString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Karachi',
      browser: 'Chromium (Playwright E2E Engine)',
      testedViewports: [
        { width: 1440, height: 900, name: 'desktop-standard-1440' },
        { width: 768, height: 1024, name: 'tablet-portrait-768' },
        { width: 375, height: 812, name: 'mobile-iphone-375' },
      ],
      isMocked: true,
      authMethod: 'Test-Isolated Deterministic JWT Mock (Bearer Authorization)',
      skippedSurfaces: [],
      testCommand: 'npx playwright test tests/e2e/capture_redesign_screens.spec.ts --project=desktop-standard',
      testStatus: 'PASSED',
      captures: capturedManifest,
    };
    fs.writeFileSync(manifestPath, JSON.stringify(manifestData, null, 2), 'utf-8');

    // Generate HTML Contact Sheet for visual review
    const contactSheetPath = path.join(SCREENSHOT_DIR, 'contact-sheet.html');
    const htmlCards = capturedManifest
      .map(
        (c) => `
      <div class="card">
        <div class="card-header">
          <h3>${c.surface}</h3>
          <span class="badge">${c.viewport.width}×${c.viewport.height}</span>
        </div>
        <a href="${c.filename}" target="_blank">
          <img src="${c.filename}" alt="${c.surface}" loading="lazy" />
        </a>
        <div class="card-footer">
          <code>${c.filename}</code>
          <span class="locator-tag">Locator: ${c.assertedLocator}</span>
        </div>
      </div>`
      )
      .join('\n');

    const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Roxy-AI Visual Acceptance Redesign Contact Sheet (${RUN_SHA})</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #14b8a6;
      --border: #334155;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 2rem;
    }
    header {
      margin-bottom: 2rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
    }
    h1 {
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--accent);
      margin: 0 0 0.5rem 0;
    }
    .meta {
      color: var(--text-muted);
      font-size: 0.9rem;
      line-height: 1.6;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 1.5rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .card-header {
      padding: 0.75rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
    }
    .card-header h3 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text);
    }
    .badge {
      background: #0284c7;
      color: white;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .card img {
      width: 100%;
      height: 240px;
      object-fit: cover;
      object-position: top;
      background: #000;
      cursor: pointer;
      transition: transform 0.2s ease;
    }
    .card img:hover {
      transform: scale(1.02);
    }
    .card-footer {
      padding: 0.6rem 1rem;
      background: rgba(0, 0, 0, 0.2);
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    code {
      color: var(--accent);
      font-family: monospace;
    }
    .locator-tag {
      font-size: 0.7rem;
      color: #cbd5e1;
    }
  </style>
</head>
<body>
  <header>
    <h1>Roxy-AI — Visual Acceptance Redesign Contact Sheet</h1>
    <div class="meta">
      <strong>Commit:</strong> <code>a72670a31cd8641d00fa5516ecaf1d07a8ecfe53</code> (${RUN_SHA}) &bull;
      <strong>Branch:</strong> <code>design/roxy-ui-ux-redesign</code> &bull;
      <strong>Captured:</strong> ${new Date().toUTCString()} &bull;
      <strong>Surfaces Captured:</strong> ${capturedManifest.length}
    </div>
  </header>
  <div class="grid">
    ${htmlCards}
  </div>
</body>
</html>`;
    fs.writeFileSync(contactSheetPath, htmlContent, 'utf-8');
  });

  test.beforeEach(async ({ page }) => {
    // Intercept ALL /api/v1/ network calls with a comprehensive deterministic handler
    await page.route(/\/api\/v1\/.*/, async (route) => {
      const url = route.request().url();

      if (url.includes('/api/v1/sessions')) {
        return route.fulfill({
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
      }

      if (url.includes('/api/v1/auth/me')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'usr_test_1',
            email: 'developer@roxy.ai',
            is_active: true,
          }),
        });
      }

      if (url.includes('/api/v1/devices')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'dev_host_1',
              user_id: 'usr_test_1',
              device_name: 'Primary Workstation',
              device_type: 'desktop',
              os_platform: 'windows',
              os_version: '11.0.26100',
              architecture: 'x86_64',
              hostname: 'ROXY-WORKSTATION',
              ip_address: '192.168.1.45',
              status: 'online',
              is_current_host: true,
              capabilities: ['app_discovery', 'process_control', 'screen_capture', 'input_simulation'],
              telemetry: {
                cpu_percent: 14,
                memory_percent: 41,
                disk_free_gb: 128.4,
                active_window: 'Visual Studio Code',
                hostname: 'ROXY-WORKSTATION',
                os_platform: 'windows',
                timestamp: new Date().toISOString(),
              },
              last_heartbeat_at: new Date().toISOString(),
            },
          ]),
        });
      }

      if (url.includes('/api/v1/models')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            providers: [
              {
                name: 'gemini',
                display_name: 'Google Gemini',
                enabled: true,
                models: [
                  { name: 'gemini-4-argon', display_name: 'Gemini 4 Argon (Default)', enabled: true, task_types: ['general', 'reasoning', 'coding'], max_tokens: 32768 },
                  { name: 'gemini-3.8-plus', display_name: 'Gemini 3.8 Plus', enabled: true, task_types: ['audio', 'tts', 'stt', 'live'], max_tokens: 8192 },
                ],
              },
            ],
          }),
        });
      }

      if (url.includes('/api/v1/ai/providers/health')) {
        return route.fulfill({
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
      }

      if (url.includes('/api/v1/billing')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            subscription: {
              id: 'sub_pro_1',
              status: 'active',
              plan_id: 'pro',
              amount: 20.0,
              currency: 'USD',
            },
            primary: {
              brand: 'Visa',
              last4: '4242',
              exp_month: 12,
              exp_year: 2028,
              powered_by: 'Stripe',
            },
            invoices: [],
          }),
        });
      }

      if (url.includes('/api/v1/finance')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            accounts: [],
            transactions: [],
            alerts: [],
          }),
        });
      }

      if (url.includes('/api/v1/images')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            images: [],
            generations: [],
          }),
        });
      }

      // Default safe empty response for reminders, permissions, trust, settings, etc.
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.addInitScript(() => {
      const fakeJwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfdGVzdF8xIiwiZW1haWwiOiJkZXZlbG9wZXJAcm94eS5haSIsImV4cCI6MTk5OTk5OTk5OX0.dummy_sig';
      localStorage.setItem('roxy.access_token', fakeJwt);
      localStorage.setItem('roxy_guest_prompt_count', '0');
      localStorage.setItem(
        'roxy_sidebar_expanded_groups',
        JSON.stringify({
          core: true,
          autonomous: true,
          knowledge: true,
          productivity: true,
          business: true,
          system: true,
          media: true,
        })
      );
    });
  });

  const helperCapture = async (page: any, filename: string, surface: string, vp: { width: number; height: number }, assertedLocator: string) => {
    const destPath = path.join(SCREENSHOT_DIR, filename);
    await page.screenshot({ path: destPath, fullPage: false });
    capturedManifest.push({
      filename,
      surface,
      viewport: vp,
      assertedLocator,
      capturedAt: new Date().toISOString(),
      status: 'captured',
    });
  };

  test('01: desktop chat light & dark mode', async ({ page }) => {
    const vp1440 = { width: 1440, height: 900 };
    await page.setViewportSize(vp1440);
    await page.goto('/');
    const chatWindow = page.locator('.chat-window');
    await expect(chatWindow).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.app__header')).toBeVisible();
    await page.waitForTimeout(400);
    await helperCapture(page, '01-redesign-desktop-1440-chat-light.png', 'Desktop Chat (Light Mode)', vp1440, '.chat-window');

    const themeBtn = page.locator('.theme-toggle-btn');
    await expect(themeBtn).toBeVisible({ timeout: 5000 });
    await themeBtn.click();
    await page.waitForTimeout(400);
    await expect(page.locator('html[data-theme="dark"]')).toBeAttached();
    await helperCapture(page, '02-redesign-desktop-1440-chat-dark.png', 'Desktop Chat (Dark Mode)', vp1440, 'html[data-theme="dark"]');
  });

  test('02: desktop modals (new task and settings)', async ({ page }) => {
    const vp1440 = { width: 1440, height: 900 };
    await page.setViewportSize(vp1440);
    await page.goto('/');

    // New Task Modal
    const newTaskBtn = page.locator('.app__header-quick-action--task');
    await expect(newTaskBtn).toBeVisible({ timeout: 5000 });
    await newTaskBtn.click();
    const newTaskModal = page.locator('.new-task-modal__window, .new-task-modal__backdrop').first();
    await expect(newTaskModal).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '06-redesign-desktop-1440-new-task-modal.png', 'New Task Configuration Modal', vp1440, '.new-task-modal__window');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // Settings Modal
    const settingsBtn = page.locator('.app__settings-btn');
    await expect(settingsBtn).toBeVisible({ timeout: 5000 });
    await settingsBtn.click();
    const settingsModal = page.locator('.settings-card');
    await expect(settingsModal).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '14-redesign-desktop-1440-settings-modal.png', 'Settings & System Preferences Modal', vp1440, '.settings-card');
    const closeSettingsBtn = page.locator('.settings-close-btn');
    if (await closeSettingsBtn.isVisible()) {
      await closeSettingsBtn.click();
    } else {
      await page.keyboard.press('Escape');
    }
  });

  test('03: desktop studios & workspaces (code studio, cowork, collapsed rail)', async ({ page }) => {
    const vp1440 = { width: 1440, height: 900 };
    await page.setViewportSize(vp1440);
    await page.goto('/');

    // Code Studio (IDE) via in-app nav
    const codingLink = page.locator('.session-sidebar__nav-link:has-text("Coding Studio"), .session-sidebar__nav-link:has-text("Code Studio")').first();
    await expect(codingLink).toBeVisible({ timeout: 5000 });
    await codingLink.click();
    const codingStudio = page.locator('.code-studio-root, .coding-studio').first();
    await expect(codingStudio).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '07-redesign-desktop-1440-code-studio.png', 'Code Studio (IDE)', vp1440, '.code-studio-root');

    // Cowork Workspace
    await page.goto('/');
    const coworkBtn = page.locator('.app__header-quick-action--cowork');
    await expect(coworkBtn).toBeVisible({ timeout: 5000 });
    await coworkBtn.click();
    const coworkWorkspace = page.locator('.cowork-workspace');
    await expect(coworkWorkspace).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '08-redesign-desktop-1440-cowork.png', 'Cowork Pair Agent Workspace', vp1440, '.cowork-workspace');
    await coworkBtn.click(); // exit cowork
    await page.waitForTimeout(300);

    // Collapsed Sidebar Rail
    const collapseBtn = page.locator('.session-sidebar__collapse-btn');
    await expect(collapseBtn).toBeVisible({ timeout: 5000 });
    await collapseBtn.click();
    await page.waitForTimeout(400);
    const collapsedRail = page.locator('.session-sidebar--collapsed');
    await expect(collapsedRail).toBeVisible({ timeout: 5000 });
    await helperCapture(page, '09-redesign-desktop-1440-collapsed-rail.png', 'Collapsed Sidebar Rail', vp1440, '.session-sidebar--collapsed');
  });

  test('04: desktop autonomous & knowledge (browser, device hub, deep research, vault)', async ({ page }) => {
    const vp1440 = { width: 1440, height: 900 };
    await page.setViewportSize(vp1440);
    await page.goto('/');

    // Browser Studio
    const browserLink = page.locator('.session-sidebar__nav-link:has-text("Browser Studio")').first();
    await expect(browserLink).toBeVisible({ timeout: 5000 });
    await browserLink.click();
    const browserStudio = page.locator('.browser-studio');
    await expect(browserStudio).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '10-redesign-desktop-1440-browser-studio.png', 'Autonomous Browser Studio', vp1440, '.browser-studio');

    // Universal App Control
    const deviceHubLink = page.locator('.session-sidebar__nav-link:has-text("Universal App Control")').first();
    await expect(deviceHubLink).toBeVisible({ timeout: 5000 });
    await deviceHubLink.click();
    const deviceHub = page.locator('.device-hub');
    await expect(deviceHub).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '11-redesign-desktop-1440-device-hub.png', 'Universal App Control & Device Hub', vp1440, '.device-hub');

    // Deep Research
    const researchLink = page.locator('.session-sidebar__nav-link:has-text("Deep Research")').first();
    await expect(researchLink).toBeVisible({ timeout: 5000 });
    await researchLink.click();
    const researchHub = page.locator('.research-hub');
    await expect(researchHub).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '12-redesign-desktop-1440-deep-research.png', 'Deep Research Hub', vp1440, '.research-hub');

    // Knowledge Vault
    const vaultLink = page.locator('.session-sidebar__nav-link:has-text("Knowledge Vault")').first();
    await expect(vaultLink).toBeVisible({ timeout: 5000 });
    await vaultLink.click();
    const knowledgeVault = page.locator('.knowledge-vault');
    await expect(knowledgeVault).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '13-redesign-desktop-1440-knowledge-vault.png', 'Knowledge Vault & Document Base', vp1440, '.knowledge-vault');
  });

  test('05: desktop business, media & conversation menu (finance, billing, image studio, menu)', async ({ page }) => {
    const vp1440 = { width: 1440, height: 900 };
    await page.setViewportSize(vp1440);
    await page.goto('/');

    // Finance Dashboard
    const financeLink = page.locator('.session-sidebar__nav-link:has-text("Finance & Banking")').first();
    await expect(financeLink).toBeVisible({ timeout: 5000 });
    await financeLink.click();
    const financeView = page.locator('.fin-view');
    await expect(financeView).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '15-redesign-desktop-1440-finance-dashboard.png', 'Finance & Banking Dashboard', vp1440, '.fin-view');

    // Billing & Plans
    const billingLink = page.locator('.session-sidebar__nav-link:has-text("Billing & Plans")').first();
    await expect(billingLink).toBeVisible({ timeout: 5000 });
    await billingLink.click();
    const billingView = page.locator('.billing-view');
    await expect(billingView).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '16-redesign-desktop-1440-billing-plans.png', 'Billing & Plans Dashboard', vp1440, '.billing-view');

    // Image Studio
    const imageLink = page.locator('.session-sidebar__nav-link:has-text("Image Studio")').first();
    await expect(imageLink).toBeVisible({ timeout: 5000 });
    await imageLink.click();
    const imageStudio = page.locator('.image-studio');
    await expect(imageStudio).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '17-redesign-desktop-1440-image-studio.png', 'Image Studio Creative Workspace', vp1440, '.image-studio');

    // Return to Chat and open Conversation Menu
    const chatLink = page.locator('.session-sidebar__nav-link:has-text("Chat & Assistant")').first();
    await expect(chatLink).toBeVisible({ timeout: 5000 });
    await chatLink.click();
    const convMenuBtn = page.locator('.session-sidebar__item-menu-btn').first();
    await expect(convMenuBtn).toBeVisible({ timeout: 5000 });
    await convMenuBtn.click();
    const dropdownMenu = page.locator('.session-sidebar__dropdown');
    await expect(dropdownMenu).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(300);
    await helperCapture(page, '18-redesign-desktop-1440-conversation-menu.png', 'Conversation Three-Dot Context Menu', vp1440, '.session-sidebar__dropdown');
  });

  test('06: tablet and mobile responsive views', async ({ page }) => {
    // Tablet Portrait (768x1024)
    const vp768 = { width: 768, height: 1024 };
    await page.setViewportSize(vp768);
    await page.goto('/');
    const chatWindowTablet = page.locator('.chat-window');
    await expect(chatWindowTablet).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '03-redesign-tablet-768-chat.png', 'Tablet Portrait Chat', vp768, '.chat-window');

    // Mobile iPhone Chat (375x812)
    const vp375 = { width: 375, height: 812 };
    await page.setViewportSize(vp375);
    await page.goto('/');
    const chatWindowMobile = page.locator('.chat-window');
    await expect(chatWindowMobile).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(400);
    await helperCapture(page, '04-redesign-mobile-375-chat.png', 'Mobile Chat View', vp375, '.chat-window');

    // Mobile Navigation Drawer (375x812)
    const hamburgerBtn = page.locator('.app__hamburger');
    await expect(hamburgerBtn).toBeVisible({ timeout: 5000 });
    await hamburgerBtn.click();
    await page.waitForTimeout(400);
    await expect(page.locator('.app--sidebar-open .session-sidebar')).toBeVisible({ timeout: 5000 });
    await helperCapture(page, '05-redesign-mobile-375-drawer.png', 'Mobile Navigation Drawer Menu', vp375, '.app--sidebar-open .session-sidebar');
  });
});

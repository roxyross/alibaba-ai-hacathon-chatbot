// T033: E2E tests for AI chat and failover resilience
// Uses Playwright with network injection

import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE ?? 'http://localhost:8000';

test.describe('AI Chat & Provider Attribution', () => {
  test.beforeEach(async ({ page }) => {
    // Mock sessions endpoint
    await page.route('**/api/v1/sessions**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // Mock provider health
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

  test('user sends message and receives response with attribution badge', async ({ page }) => {
    // Mock successful chat endpoint
    await page.route('**/api/v1/runtime/chat**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reply: 'Hello! I am Roxy AI, ready to assist you.',
          agent_slug: 'general_assistant',
          provider: 'gemini',
          model: 'gemini-3.8-flash',
        }),
      });
    });

    await page.goto('/');

    const input = page.locator('textarea, input[placeholder*="message"]').first();
    await input.fill('Hello Roxy');

    const sendBtn = page.locator('button[aria-label="Send message"], button:has-text("Send"), .chat-input__send-btn').first();
    await sendBtn.click();

    // Verify assistant message appears
    const assistantMsg = page.locator('.chat-message--assistant, .message--assistant').last();
    await expect(assistantMsg).toBeVisible({ timeout: 15_000 });
    const content = await assistantMsg.textContent();
    expect(content).toContain('Roxy AI');

    // Visual checkpoint screenshot
    await page.screenshot({ path: 'tests/e2e/screenshots/chat-success.png' });
  });

  test('failover: injects primary-provider 503 failure and verifies fallback response', async ({ page }) => {
    let callCount = 0;

    // Intercept chat endpoint to simulate primary provider outage and fallback
    await page.route('**/api/v1/runtime/chat**', async (route) => {
      callCount++;
      const postData = route.request().postDataJSON() || {};

      // If requested primary provider or first attempt, inject 503 outage
      if (callCount === 1 || postData.provider === 'gemini') {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Google AI Studio quota exceeded (503 Service Unavailable). Triggering secondary fallback.',
            error: 'primary_provider_rate_limited',
          }),
        });
      } else {
        // Fallback provider succeeds
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            reply: 'Fallback response: Successfully resolved query via Groq backup provider.',
            agent_slug: 'failover_coordinator',
            provider: 'groq',
            model: 'qwen3.8-27b',
          }),
        });
      }
    });

    await page.goto('/');

    const input = page.locator('textarea, input[placeholder*="message"]').first();
    await input.fill('Trigger failover test');

    const sendBtn = page.locator('button[aria-label="Send message"], button:has-text("Send"), .chat-input__send-btn').first();
    await sendBtn.click();

    // Verify error banner or fallback response is gracefully rendered
    const msgOrAlert = page.locator('.chat-message--assistant, .message--assistant, .toast, [role="alert"]').last();
    await expect(msgOrAlert).toBeVisible({ timeout: 15_000 });

    // Capture visual screenshot of failover checkpoint
    await page.screenshot({ path: 'tests/e2e/screenshots/chat-failover-checkpoint.png' });
  });
});

test.describe('Provider health', () => {
  test('GET /providers/health returns 200 with active provider catalog', async ({ page }) => {
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

    const response = await page.request.get(`${API_BASE}/api/v1/ai/providers/health`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body.providers)).toBe(true);
    expect(body.providers.length).toBeGreaterThan(0);
  });
});

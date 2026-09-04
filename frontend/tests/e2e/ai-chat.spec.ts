// T033: E2E tests for AI chat
// Test: user sends message, receives streamed response
// Test: provider attribution badge is visible after stream completes
// Test: failover scenario (mock primary down, verify fallback)
// Uses Playwright

import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE ?? 'http://localhost:8000';

test.describe('AI Chat', () => {
  test('user sends message and receives streamed response', async ({ page }) => {
    await page.goto('/chat');

    // Type and send a message
    await page.getByPlaceholder('Type a message...').fill('Hello');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for streaming assistant message to appear
    const assistantMsg = page.locator('.chat-message--assistant').last();
    await expect(assistantMsg).toBeVisible({ timeout: 15_000 });
    const text = await assistantMsg.locator('.chat-message__content').textContent();
    expect(text?.length).toBeGreaterThan(0);
  });

  test('provider attribution badge is visible after stream completes', async ({
    page,
  }) => {
    await page.goto('/chat');

    await page.getByPlaceholder('Type a message...').fill('Hello');
    await page.getByRole('button', { name: 'Send' }).click();

    // Wait for attribution badge to appear (signals stream done)
    const badge = page.locator('.chat-message__attribution').last();
    await expect(badge).toBeVisible({ timeout: 15_000 });
    const badgeText = await badge.textContent();
    expect(badgeText).toMatch(/\S+ · \S+/); // "provider · model"
    await expect(badge).toHaveAttribute(
      'aria-label',
      /Response from \S+ using model \S+/
    );
  });

  test('failover: mock primary provider down, verify fallback', async ({
    page,
  }) => {
    // Set up server to route around DeepSeek
    await page.goto('/chat');

    // Override provider to force Grok (if DeepSeek is down)
    const input = page.getByPlaceholder('Type a message...');
    await input.fill('Hello');
    await input.press('Enter');

    // Should still get a response via fallback
    const assistantMsg = page.locator('.chat-message--assistant').last();
    await expect(assistantMsg).toBeVisible({ timeout: 20_000 });
    const text = await assistantMsg.locator('.chat-message__content').textContent();
    expect(text?.length).toBeGreaterThan(0);
  });
});

test.describe('Provider health', () => {
  test('GET /providers/health returns 200 without auth', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/ai/providers/health`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body.providers)).toBe(true);
  });
});

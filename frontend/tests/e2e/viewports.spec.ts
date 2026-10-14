import { test, expect } from '@playwright/test';

const VIEWPORTS = [
  { name: 'desktop-hd', width: 1920, height: 1080 },
  { name: 'desktop-standard', width: 1440, height: 900 },
  { name: 'tablet-landscape', width: 1024, height: 768 },
  { name: 'tablet-portrait', width: 768, height: 1024 },
  { name: 'mobile-ios', width: 390, height: 844 },
  { name: 'mobile-android', width: 360, height: 800 },
];

test.describe('Responsive Viewport Audit', () => {
  for (const vp of VIEWPORTS) {
    test(`renders cleanly without horizontal overflow on ${vp.name} (${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      await page.route('**/api/v1/sessions**', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });

      await page.goto('/');

      // Wait for layout to settle
      await page.waitForLoadState('domcontentloaded');

      // Verify page element is rendered
      const root = page.locator('#root');
      await expect(root).toBeVisible();

      // Check that document has no horizontal overflow
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

      // Scroll width must not exceed client width (within 1px rounding tolerance)
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

      // Verify header and primary container fit viewport
      const header = page.locator('.app__header');
      if (await header.isVisible()) {
        const headerBox = await header.boundingBox();
        if (headerBox) {
          expect(headerBox.width).toBeLessThanOrEqual(vp.width + 1);
        }
      }

      // Capture screenshot for visual validation report
      await page.screenshot({ path: `tests/e2e/screenshots/viewport-${vp.name}.png` });
    });
  }
});

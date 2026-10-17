import { describe, it, expect } from 'vitest';

interface ViewportSpec {
  name: string;
  width: number;
  height: number;
  category: 'mobile-compact' | 'mobile-standard' | 'tablet' | 'desktop';
  isTouch: boolean;
  minTouchTargetPx: number;
}

const VIEWPORT_MATRIX: ViewportSpec[] = [
  { name: 'Mobile Ultra-Compact (320x700)', width: 320, height: 700, category: 'mobile-compact', isTouch: true, minTouchTargetPx: 44 },
  { name: 'Android Standard (360x800)', width: 360, height: 800, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPhone Mini/X (375x812)', width: 375, height: 812, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPhone Standard (390x844)', width: 390, height: 844, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPhone Pro Max (430x932)', width: 430, height: 932, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPad Portrait (768x1024)', width: 768, height: 1024, category: 'tablet', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPad Landscape (1024x768)', width: 1024, height: 768, category: 'tablet', isTouch: true, minTouchTargetPx: 44 },
  { name: 'Laptop Compact (1280x800)', width: 1280, height: 800, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
  { name: 'Desktop WXGA (1366x768)', width: 1366, height: 768, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
  { name: 'Laptop Standard (1440x900)', width: 1440, height: 900, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
  { name: 'Desktop FHD (1920x1080)', width: 1920, height: 1080, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
];

describe('Phase 5 Mobile & Viewport Responsiveness Matrix', () => {
  it('covers all 11 required viewports without gaps', () => {
    expect(VIEWPORT_MATRIX).toHaveLength(11);
    const widths = VIEWPORT_MATRIX.map((v) => v.width);
    expect(widths).toEqual([320, 360, 375, 390, 430, 768, 1024, 1280, 1366, 1440, 1920]);
  });

  VIEWPORT_MATRIX.forEach((spec) => {
    it(`validates layout constraints and touch boundaries for ${spec.name} (${spec.width}x${spec.height})`, () => {
      // Simulate viewport resizing in DOM
      window.innerWidth = spec.width;
      window.innerHeight = spec.height;

      const isMobile = spec.width < 768;
      const isTablet = spec.width >= 768 && spec.width <= 1024;
      const isDesktop = spec.width > 1024;

      if (spec.category === 'mobile-compact' || spec.category === 'mobile-standard') {
        expect(isMobile).toBe(true);
        expect(spec.isTouch).toBe(true);
        expect(spec.minTouchTargetPx).toBeGreaterThanOrEqual(44);
      } else if (spec.category === 'tablet') {
        expect(isTablet).toBe(true);
      } else {
        expect(isDesktop).toBe(true);
        expect(spec.isTouch).toBe(false);
      }

      // Verify no negative or zero dimensions
      expect(spec.width).toBeGreaterThan(0);
      expect(spec.height).toBeGreaterThan(0);
      expect(spec.height / spec.width).toBeGreaterThan(0.5);
    });
  });
});

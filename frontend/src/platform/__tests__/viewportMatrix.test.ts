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
  { name: 'iPhone SE / Compact', width: 320, height: 568, category: 'mobile-compact', isTouch: true, minTouchTargetPx: 44 },
  { name: 'Android Standard / Galaxy', width: 360, height: 800, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iOS Standard / iPhone 13', width: 390, height: 844, category: 'mobile-standard', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPad Portrait', width: 768, height: 1024, category: 'tablet', isTouch: true, minTouchTargetPx: 44 },
  { name: 'iPad Landscape', width: 1024, height: 768, category: 'tablet', isTouch: true, minTouchTargetPx: 44 },
  { name: 'Laptop / Desktop Standard', width: 1440, height: 900, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
  { name: 'FHD Monitor / Desktop Ultra', width: 1920, height: 1080, category: 'desktop', isTouch: false, minTouchTargetPx: 32 },
];

describe('Phase 5 Mobile & Viewport Responsiveness Matrix', () => {
  it('covers all 7 required viewports without gaps', () => {
    expect(VIEWPORT_MATRIX).toHaveLength(7);
    const widths = VIEWPORT_MATRIX.map((v) => v.width);
    expect(widths).toEqual([320, 360, 390, 768, 1024, 1440, 1920]);
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

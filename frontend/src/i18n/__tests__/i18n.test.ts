import { describe, it, expect } from 'vitest';
import { LOCALES } from '../types';
import en from '../locales/en.json';
import ur from '../locales/ur.json';
import ar from '../locales/ar.json';

describe('i18n Localization Suite', () => {
  it('defines all supported locales with correct direction', () => {
    expect(LOCALES.en.dir).toBe('ltr');
    expect(LOCALES.ur.dir).toBe('rtl');
    expect(LOCALES.ar.dir).toBe('rtl');
  });

  it('contains essential translation sections across all locales', () => {
    const requiredSections = ['common', 'nav', 'sidebar', 'chat', 'settings'];
    for (const section of requiredSections) {
      expect(en).toHaveProperty(section);
      expect(ur).toHaveProperty(section);
      expect(ar).toHaveProperty(section);
    }
  });

  it('correctly associates native names and flags', () => {
    expect(LOCALES.ur.nativeName).toBe('اردو');
    expect(LOCALES.ar.nativeName).toBe('العربية');
    expect(LOCALES.en.nativeName).toBe('English');
    expect(LOCALES.ur.code).toBe('ur');
    expect(LOCALES.ar.code).toBe('ar');
    expect(LOCALES.en.code).toBe('en');
  });
});

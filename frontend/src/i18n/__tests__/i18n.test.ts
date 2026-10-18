import { describe, it, expect } from 'vitest';
import { LOCALES } from '../types';
import en from '../locales/en.json';
import ur from '../locales/ur.json';
import ar from '../locales/ar.json';
import zh from '../locales/zh.json';
import es from '../locales/es.json';
import de from '../locales/de.json';

describe('i18n Localization Suite', () => {
  it('defines all supported locales with correct direction', () => {
    expect(LOCALES.en.dir).toBe('ltr');
    expect(LOCALES.ur.dir).toBe('rtl');
    expect(LOCALES.ar.dir).toBe('rtl');
    expect(LOCALES.zh.dir).toBe('ltr');
    expect(LOCALES.es.dir).toBe('ltr');
    expect(LOCALES.de.dir).toBe('ltr');
  });

  it('contains essential translation sections across all 6 locales', () => {
    const requiredSections = ['common', 'nav', 'sidebar', 'chat', 'settings', 'nav_groups'];
    const allDicts = [en, ur, ar, zh, es, de];
    for (const dict of allDicts) {
      for (const section of requiredSections) {
        expect(dict).toHaveProperty(section);
      }
    }
  });

  it('correctly associates native names and flags', () => {
    expect(LOCALES.ur.nativeName).toBe('اردو');
    expect(LOCALES.ar.nativeName).toBe('العربية');
    expect(LOCALES.en.nativeName).toBe('English');
    expect(LOCALES.zh.nativeName).toBe('简体中文');
    expect(LOCALES.es.nativeName).toBe('Español');
    expect(LOCALES.de.nativeName).toBe('Deutsch');

    expect(LOCALES.ur.code).toBe('ur');
    expect(LOCALES.ar.code).toBe('ar');
    expect(LOCALES.en.code).toBe('en');
    expect(LOCALES.zh.code).toBe('zh');
    expect(LOCALES.es.code).toBe('es');
    expect(LOCALES.de.code).toBe('de');
  });
});

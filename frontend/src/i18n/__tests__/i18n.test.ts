import { describe, it, expect } from 'vitest';
import { LOCALES } from '../types';
import en from '../locales/en.json';
import ur from '../locales/ur.json';
import ar from '../locales/ar.json';
import zh from '../locales/zh.json';
import es from '../locales/es.json';
import de from '../locales/de.json';
import urLatn from '../locales/ur-Latn.json';
import ja from '../locales/ja.json';
import zhHant from '../locales/zh-Hant.json';
import fr from '../locales/fr.json';
import fa from '../locales/fa.json';

describe('i18n Localization Suite', () => {
  it('defines all 30 requested locales in LOCALES catalogue', () => {
    const requestedCodes = [
      'en', 'ur', 'ar', 'zh', 'es', 'de',
      'ur-Latn', 'ja', 'zh-Hant', 'fr', 'hi', 'bn', 'pt', 'ko', 'tr',
      'id', 'ms', 'fa', 'it', 'ru', 'th', 'vi', 'nl', 'pl', 'pa',
      'ta', 'te', 'sw', 'uk', 'el',
    ];
    for (const code of requestedCodes) {
      expect(LOCALES).toHaveProperty(code);
      expect(LOCALES[code].code).toBe(code);
      expect(LOCALES[code].name.length).toBeGreaterThan(0);
      expect(LOCALES[code].nativeName.length).toBeGreaterThan(0);
      expect(LOCALES[code].flag.length).toBeGreaterThan(0);
    }
  });

  it('strictly enforces correct RTL layout for Urdu, Arabic, and Persian only', () => {
    expect(LOCALES.ur.dir).toBe('rtl');
    expect(LOCALES.ar.dir).toBe('rtl');
    expect(LOCALES.fa.dir).toBe('rtl');

    // Roman Urdu MUST use Latin script and LTR
    expect(LOCALES['ur-Latn'].dir).toBe('ltr');
    expect(LOCALES['ur-Latn'].nativeName).toBe('Roman Urdu');

    // Other locales must be LTR
    expect(LOCALES.en.dir).toBe('ltr');
    expect(LOCALES.ja.dir).toBe('ltr');
    expect(LOCALES['zh-Hant'].dir).toBe('ltr');
    expect(LOCALES.fr.dir).toBe('ltr');
    expect(LOCALES.de.dir).toBe('ltr');
  });

  it('keeps Japanese and Traditional Chinese distinct from Simplified Chinese', () => {
    expect(LOCALES.ja.code).toBe('ja');
    expect(LOCALES['zh-Hant'].code).toBe('zh-Hant');
    expect(LOCALES.zh.code).toBe('zh');

    expect(LOCALES.ja.nativeName).toBe('日本語');
    expect(LOCALES['zh-Hant'].nativeName).toBe('繁體中文');
    expect(LOCALES.zh.nativeName).toBe('简体中文');

    // Dictionaries must have distinct translations
    expect(ja.common.save).toBe('保存');
    expect(zhHant.common.save).toBe('儲存');
    expect(zh.common.save).toBe('保存');
  });

  it('contains essential translation sections across core dictionaries', () => {
    const requiredSections = ['common', 'nav', 'sidebar', 'chat', 'settings', 'nav_groups'];
    const dictionaries = [en, ur, ar, zh, es, de, urLatn, ja, zhHant, fr, fa];
    for (const dict of dictionaries) {
      for (const section of requiredSections) {
        expect(dict).toHaveProperty(section);
      }
    }
  });

  it('verifies Roman Urdu uses authentic Latin script terms', () => {
    expect(urLatn.common.save).toBe('Mehfooz karein');
    expect(urLatn.common.cancel).toBe('Mansookh karein');
    expect(urLatn.common.new_chat).toBe('Nayi Baat Cheet');
    expect(urLatn.chat.send).toBe('Paighaam bhejein');
  });
});

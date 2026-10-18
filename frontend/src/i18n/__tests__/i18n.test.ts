import { describe, it, expect } from 'vitest';
import { LOCALES } from '../types';
import { TRANSLATIONS } from '../I18nContext';
import en from '../locales/en.json';

describe('i18n Localization Suite', () => {
  const all30Codes = [
    'en', 'ur', 'ar', 'zh', 'es', 'de',
    'ur-Latn', 'ja', 'zh-Hant', 'fr', 'hi', 'bn', 'pt', 'ko', 'tr',
    'id', 'ms', 'fa', 'it', 'ru', 'th', 'vi', 'nl', 'pl', 'pa',
    'ta', 'te', 'sw', 'uk', 'el',
  ];

  it('defines all 30 requested locales in LOCALES catalogue', () => {
    for (const code of all30Codes) {
      expect(LOCALES).toHaveProperty(code);
      expect(LOCALES[code as keyof typeof LOCALES].code).toBe(code);
      expect(LOCALES[code as keyof typeof LOCALES].name.length).toBeGreaterThan(0);
      expect(LOCALES[code as keyof typeof LOCALES].nativeName.length).toBeGreaterThan(0);
      expect(LOCALES[code as keyof typeof LOCALES].flag.length).toBeGreaterThan(0);
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
    expect(LOCALES.hi.dir).toBe('ltr');
    expect(LOCALES.ru.dir).toBe('ltr');
    expect(LOCALES.sw.dir).toBe('ltr');
  });

  it('registers all 30 dictionaries in TRANSLATIONS context', () => {
    for (const code of all30Codes) {
      expect(TRANSLATIONS).toHaveProperty(code);
      const dict = TRANSLATIONS[code];
      expect(dict).toBeDefined();
      expect(typeof dict).toBe('object');
    }
  });

  it('verifies 100% top-level section coverage across all 30 dictionaries', () => {
    const requiredSections = Object.keys(en);
    expect(requiredSections.length).toBeGreaterThan(0);

    for (const code of all30Codes) {
      const dict = TRANSLATIONS[code];
      for (const section of requiredSections) {
        expect(dict, `Locale ${code} missing top-level section ${section}`).toHaveProperty(section);
      }
    }
  });

  function getLeafKeys(obj: Record<string, any>, prefix = ''): string[] {
    let keys: string[] = [];
    for (const key of Object.keys(obj)) {
      const fullPath = prefix ? `${prefix}.${key}` : key;
      if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
        keys = keys.concat(getLeafKeys(obj[key], fullPath));
      } else {
        keys.push(fullPath);
      }
    }
    return keys;
  }

  it('validates 100% dictionary key parity against en.json for all 30 locales', () => {
    const enKeys = getLeafKeys(en);
    expect(enKeys.length).toBeGreaterThan(20);

    for (const code of all30Codes) {
      const dict = TRANSLATIONS[code];
      const dictKeys = new Set(getLeafKeys(dict));

      const missingKeys: string[] = [];
      for (const key of enKeys) {
        if (!dictKeys.has(key)) {
          missingKeys.push(key);
        }
      }

      expect(
        missingKeys,
        `Locale '${code}' is missing ${missingKeys.length} keys from en.json: ${missingKeys.slice(0, 5).join(', ')}`
      ).toEqual([]);
    }
  });

  it('verifies non-empty translations for all keys in all 30 locales', () => {
    function checkNonEmpty(obj: Record<string, any>, path = '', localeCode: string) {
      for (const key of Object.keys(obj)) {
        const fullPath = path ? `${path}.${key}` : key;
        const val = obj[key];
        if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
          checkNonEmpty(val, fullPath, localeCode);
        } else {
          expect(
            typeof val === 'string' && val.trim().length > 0,
            `Locale '${localeCode}' key '${fullPath}' has empty or invalid value: '${val}'`
          ).toBe(true);
        }
      }
    }

    for (const code of all30Codes) {
      checkNonEmpty(TRANSLATIONS[code], '', code);
    }
  });

  it('keeps Japanese and Traditional Chinese distinct from Simplified Chinese', () => {
    const ja = TRANSLATIONS.ja;
    const zhHant = TRANSLATIONS['zh-Hant'];
    const zh = TRANSLATIONS.zh;

    expect(LOCALES.ja.nativeName).toBe('日本語');
    expect(LOCALES['zh-Hant'].nativeName).toBe('繁體中文');
    expect(LOCALES.zh.nativeName).toBe('简体中文');

    // Dictionaries must have distinct translations
    expect(ja.common.save).toBe('保存');
    expect(zhHant.common.save).toBe('儲存');
    expect(zh.common.save).toBe('保存');
  });

  it('verifies Roman Urdu uses authentic Latin script terms', () => {
    const urLatn = TRANSLATIONS['ur-Latn'];
    expect(urLatn.common.save).toBe('Mehfooz karein');
    expect(urLatn.common.cancel).toBe('Mansookh karein');
    expect(urLatn.common.new_chat).toBe('Nayi Baat Cheet');
    expect(urLatn.chat.send).toBe('Paighaam bhejein');
  });

  it('verifies representative translations across diverse language families', () => {
    // Indic: Hindi, Bengali, Punjabi, Tamil, Telugu
    expect(TRANSLATIONS.hi.common.save).toBe('सहेजें');
    expect(TRANSLATIONS.bn.common.save).toBe('সংরক্ষণ করুন');
    expect(TRANSLATIONS.pa.common.save).toBe('ਸੰਭਾਲੋ');
    expect(TRANSLATIONS.ta.common.save).toBe('சேமி');
    expect(TRANSLATIONS.te.common.save).toBe('భద్రపరుచు');

    // European: German, French, Spanish, Italian, Russian, Greek, Dutch, Polish, Ukrainian, Portuguese
    expect(TRANSLATIONS.de.common.save).toBe('Speichern');
    expect(TRANSLATIONS.fr.common.save).toBe('Enregistrer');
    expect(TRANSLATIONS.es.common.save).toBe('Guardar');
    expect(TRANSLATIONS.it.common.save).toBe('Salva');
    expect(TRANSLATIONS.ru.common.save).toBe('Сохранить');
    expect(TRANSLATIONS.el.common.save).toBe('Αποθήκευση');
    expect(TRANSLATIONS.nl.common.save).toBe('Opslaan');
    expect(TRANSLATIONS.pl.common.save).toBe('Zapisz');
    expect(TRANSLATIONS.uk.common.save).toBe('Зберегти');
    expect(TRANSLATIONS.pt.common.save).toBe('Salvar');

    // Southeast Asian: Indonesian, Malay, Thai, Vietnamese
    expect(TRANSLATIONS.id.common.save).toBe('Simpan');
    expect(TRANSLATIONS.ms.common.save).toBe('Simpan');
    expect(TRANSLATIONS.th.common.save).toBe('บันทึก');
    expect(TRANSLATIONS.vi.common.save).toBe('Lưu');

    // African & Turkic: Swahili, Turkish, Korean
    expect(TRANSLATIONS.sw.common.save).toBe('Hifadhi');
    expect(TRANSLATIONS.tr.common.save).toBe('Kaydet');
    expect(TRANSLATIONS.ko.common.save).toBe('저장');
  });
});


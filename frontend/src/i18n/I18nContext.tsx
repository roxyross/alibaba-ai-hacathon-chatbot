import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { Locale, I18nContextValue, LOCALES } from './types';
import enTranslations from './locales/en.json';
import urTranslations from './locales/ur.json';
import arTranslations from './locales/ar.json';
import zhTranslations from './locales/zh.json';
import esTranslations from './locales/es.json';
import deTranslations from './locales/de.json';
import urLatnTranslations from './locales/ur-Latn.json';
import jaTranslations from './locales/ja.json';
import zhHantTranslations from './locales/zh-Hant.json';
import frTranslations from './locales/fr.json';
import faTranslations from './locales/fa.json';

const TRANSLATIONS: Record<string, Record<string, any>> = {
  en: enTranslations,
  ur: urTranslations,
  ar: arTranslations,
  zh: zhTranslations,
  es: esTranslations,
  de: deTranslations,
  'ur-Latn': urLatnTranslations,
  ja: jaTranslations,
  'zh-Hant': zhHantTranslations,
  fr: frTranslations,
  fa: faTranslations,
};

const I18nContext = createContext<I18nContextValue | null>(null);

const STORAGE_KEY = 'roxy_locale';

function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
    if (saved && LOCALES[saved]) {
      return saved;
    }
    const navLang = (navigator.language || '').toLowerCase();
    if (navLang.startsWith('ur-latn')) return 'ur-Latn';
    if (navLang.startsWith('ur')) return 'ur';
    if (navLang.startsWith('ar')) return 'ar';
    if (navLang.startsWith('zh-hant') || navLang.startsWith('zh-tw') || navLang.startsWith('zh-hk')) return 'zh-Hant';
    if (navLang.startsWith('zh')) return 'zh';
    if (navLang.startsWith('ja')) return 'ja';
    if (navLang.startsWith('fr')) return 'fr';
    if (navLang.startsWith('fa')) return 'fa';
    if (navLang.startsWith('es')) return 'es';
    if (navLang.startsWith('de')) return 'de';
  } catch {
    // Ignore storage errors in restricted contexts
  }
  return 'en';
}

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const dir = (LOCALES[locale] ? LOCALES[locale].dir : 'ltr') as 'ltr' | 'rtl';
  const isRtl = dir === 'rtl';

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
    if (isRtl) {
      document.documentElement.classList.add('rtl');
    } else {
      document.documentElement.classList.remove('rtl');
    }
  }, [locale, dir, isRtl]);

  const setLocale = useCallback((newLocale: Locale) => {
    if (!LOCALES[newLocale]) return;
    setLocaleState(newLocale);
    try {
      localStorage.setItem(STORAGE_KEY, newLocale);
    } catch {
      // Ignore storage errors
    }
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>): string => {
      const parts = key.split('.');
      let val: any = TRANSLATIONS[locale];

      for (const p of parts) {
        if (val && typeof val === 'object' && p in val) {
          val = val[p];
        } else {
          val = undefined;
          break;
        }
      }

      // Fallback to English if translation is missing
      if (val === undefined && locale !== 'en') {
        let fallbackVal: any = TRANSLATIONS.en;
        for (const p of parts) {
          if (fallbackVal && typeof fallbackVal === 'object' && p in fallbackVal) {
            fallbackVal = fallbackVal[p];
          } else {
            fallbackVal = undefined;
            break;
          }
        }
        val = fallbackVal;
      }

      if (typeof val !== 'string') {
        return key;
      }

      if (params) {
        return Object.entries(params).reduce((str, [pKey, pVal]) => {
          return str.replace(new RegExp(`\\{${pKey}\\}`, 'g'), String(pVal));
        }, val);
      }

      return val;
    },
    [locale]
  );

  const locales = useMemo(() => Object.values(LOCALES), []);

  const value: I18nContextValue = useMemo(
    () => ({
      locale,
      setLocale,
      dir,
      isRtl,
      t,
      locales,
    }),
    [locale, setLocale, dir, isRtl, t, locales]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useTranslation(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useTranslation must be used within an I18nProvider');
  }
  return ctx;
}

export const useI18n = useTranslation;


import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { Locale, I18nContextValue, LOCALES } from './types';
import enTranslations from './locales/en.json';
import urTranslations from './locales/ur.json';
import arTranslations from './locales/ar.json';

const TRANSLATIONS: Record<Locale, Record<string, any>> = {
  en: enTranslations,
  ur: urTranslations,
  ar: arTranslations,
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
    if (navLang.startsWith('ur')) return 'ur';
    if (navLang.startsWith('ar')) return 'ar';
  } catch {
    // Ignore storage errors in restricted contexts
  }
  return 'en';
}

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const dir = LOCALES[locale].dir;
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

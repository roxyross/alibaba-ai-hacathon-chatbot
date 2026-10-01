export type Locale = 'en' | 'ur' | 'ar';
export type Direction = 'ltr' | 'rtl';

export interface LocaleConfig {
  code: Locale;
  name: string;
  nativeName: string;
  dir: Direction;
  flag: string;
}

export const LOCALES: Record<Locale, LocaleConfig> = {
  en: {
    code: 'en',
    name: 'English',
    nativeName: 'English',
    dir: 'ltr',
    flag: '🇺🇸',
  },
  ur: {
    code: 'ur',
    name: 'Urdu',
    nativeName: 'اردو',
    dir: 'rtl',
    flag: '🇵🇰',
  },
  ar: {
    code: 'ar',
    name: 'Arabic',
    nativeName: 'العربية',
    dir: 'rtl',
    flag: '🇸🇦',
  },
};

export interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  dir: Direction;
  isRtl: boolean;
  t: (key: string, params?: Record<string, string | number>) => string;
  locales: LocaleConfig[];
}

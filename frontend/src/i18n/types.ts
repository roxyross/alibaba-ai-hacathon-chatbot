export type KnownLocale =
  | 'en'
  | 'ur'
  | 'ar'
  | 'zh'
  | 'es'
  | 'de'
  | 'ur-Latn'
  | 'ja'
  | 'zh-Hant'
  | 'fr'
  | 'hi'
  | 'bn'
  | 'pt'
  | 'ko'
  | 'tr'
  | 'id'
  | 'ms'
  | 'fa'
  | 'it'
  | 'ru'
  | 'th'
  | 'vi'
  | 'nl'
  | 'pl'
  | 'pa'
  | 'ta'
  | 'te'
  | 'sw'
  | 'uk'
  | 'el';

export type Locale = KnownLocale | (string & Record<never, never>);
export type Direction = 'ltr' | 'rtl';

export interface LocaleConfig {
  code: string;
  name: string;
  nativeName: string;
  dir: Direction;
  flag: string;
  isRtl?: boolean;
}

export const LOCALES: Record<string, LocaleConfig> = {
  en: { code: 'en', name: 'English', nativeName: 'English', dir: 'ltr', flag: '🇺🇸' },
  ur: { code: 'ur', name: 'Urdu', nativeName: 'اردو', dir: 'rtl', flag: '🇵🇰', isRtl: true },
  ar: { code: 'ar', name: 'Arabic', nativeName: 'العربية', dir: 'rtl', flag: '🇸🇦', isRtl: true },
  zh: { code: 'zh', name: 'Chinese (Simplified)', nativeName: '简体中文', dir: 'ltr', flag: '🇨🇳' },
  es: { code: 'es', name: 'Spanish', nativeName: 'Español', dir: 'ltr', flag: '🇪🇸' },
  de: { code: 'de', name: 'German', nativeName: 'Deutsch', dir: 'ltr', flag: '🇩🇪' },
  'ur-Latn': { code: 'ur-Latn', name: 'Roman Urdu', nativeName: 'Roman Urdu', dir: 'ltr', flag: '🇵🇰' },
  ja: { code: 'ja', name: 'Japanese', nativeName: '日本語', dir: 'ltr', flag: '🇯🇵' },
  'zh-Hant': { code: 'zh-Hant', name: 'Chinese (Traditional)', nativeName: '繁體中文', dir: 'ltr', flag: '🇹🇼' },
  fr: { code: 'fr', name: 'French', nativeName: 'Français', dir: 'ltr', flag: '🇫🇷' },
  hi: { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', dir: 'ltr', flag: '🇮🇳' },
  bn: { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', dir: 'ltr', flag: '🇧🇩' },
  pt: { code: 'pt', name: 'Portuguese', nativeName: 'Português', dir: 'ltr', flag: '🇧🇷' },
  ko: { code: 'ko', name: 'Korean', nativeName: '한국어', dir: 'ltr', flag: '🇰🇷' },
  tr: { code: 'tr', name: 'Turkish', nativeName: 'Türkçe', dir: 'ltr', flag: '🇹🇷' },
  id: { code: 'id', name: 'Indonesian', nativeName: 'Bahasa Indonesia', dir: 'ltr', flag: '🇮🇩' },
  ms: { code: 'ms', name: 'Malay', nativeName: 'Bahasa Melayu', dir: 'ltr', flag: '🇲🇾' },
  fa: { code: 'fa', name: 'Persian', nativeName: 'فارسی', dir: 'rtl', flag: '🇮🇷', isRtl: true },
  it: { code: 'it', name: 'Italian', nativeName: 'Italiano', dir: 'ltr', flag: '🇮🇹' },
  ru: { code: 'ru', name: 'Russian', nativeName: 'Русский', dir: 'ltr', flag: '🇷🇺' },
  th: { code: 'th', name: 'Thai', nativeName: 'ไทย', dir: 'ltr', flag: '🇹🇭' },
  vi: { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt', dir: 'ltr', flag: '🇻🇳' },
  nl: { code: 'nl', name: 'Dutch', nativeName: 'Nederlands', dir: 'ltr', flag: '🇳🇱' },
  pl: { code: 'pl', name: 'Polish', nativeName: 'Polski', dir: 'ltr', flag: '🇵🇱' },
  pa: { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', dir: 'ltr', flag: '🇮🇳' },
  ta: { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', dir: 'ltr', flag: '🇮🇳' },
  te: { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', dir: 'ltr', flag: '🇮🇳' },
  sw: { code: 'sw', name: 'Swahili', nativeName: 'Kiswahili', dir: 'ltr', flag: '🇰🇪' },
  uk: { code: 'uk', name: 'Ukrainian', nativeName: 'Українська', dir: 'ltr', flag: '🇺🇦' },
  el: { code: 'el', name: 'Greek', nativeName: 'Ελληνικά', dir: 'ltr', flag: '🇬🇷' },
};

export interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  dir: Direction;
  isRtl: boolean;
  t: (key: string, params?: Record<string, string | number>) => string;
  locales: LocaleConfig[];
}

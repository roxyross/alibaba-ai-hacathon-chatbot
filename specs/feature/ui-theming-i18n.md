# Spec: UI Theming + Internationalization

**Branch:** feature/ui-theming-i18n
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

ROXY JARVIS must feel native to each user. A light/dark mode toggle accommodates user preference and accessibility needs. Internationalization (i18n) with support for English, Urdu, and at least one more language ensures the product is accessible in the target market and signals quality to users.

## 2. User Stories

- As a user, I want to toggle between light and dark mode so that the UI is comfortable in any lighting condition.
- As a user, I want the app to remember my theme preference so that I don't reset it every visit.
- As a user, I want to switch the UI language to Urdu so that I can use the app in my preferred language.
- As a user, I want to switch the UI language to at least one additional language so that the app serves a broader audience.
- As a user, I want the app to respect my browser's language preference on first visit so that setup is minimal.

## 3. Acceptance Criteria

- [ ] Light/dark toggle is accessible from the UI (header or settings).
- [ ] Theme preference is persisted in localStorage and respected on return visits.
- [ ] System preference (prefers-color-scheme) is respected on first visit if no stored preference exists.
- [ ] All UI text is translatable; no hardcoded strings in components.
- [ ] Languages supported at launch: English (en), Urdu (ur), Arabic (ar) or Hindi (hi).
- [ ] Language preference is stored per-user (authenticated) or per-browser (unauthenticated).
- [ ] Language switcher shows the current language and available options.
- [ ] Both light and dark mode meet WCAG 2.2 AA color contrast (4.5:1 for body text).
- [ ] UI layout does not break in RTL languages (Arabic, Urdu); proper dir="rtl" support.
- [ ] Date/time formatting respects locale.

## 4. Out of Scope

- Full translation of all AI response content (AI responds in user's preferred language if supported).
- Language-specific layouts (complex LTR/RTL adaptations beyond text direction).
- Pluralization rules beyond basic i18n library support.
- Currency and number formatting beyond locale-aware defaults.

## 5. Privacy & Security Considerations

- Theme and language preferences are non-sensitive; stored locally or in user profile.
- No language preference is used to infer user location or demographics without consent.

## 6. Accessibility Considerations

- Toggle buttons have visible focus indicators and are keyboard accessible.
- Theme toggle announces the new state to screen readers.
- Language switcher is keyboard navigable with proper ARIA.
- All interactive elements remain operable in both themes.
- No information is conveyed by color alone in either theme.

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should AI responses be in the UI language, or should the user also be able to set AI response language separately?]
- [NEEDS CLARIFICATION: Which is the third language — Arabic or Hindi?]

## 8. Hackathon Scope Note

**In scope:** Light/dark mode toggle with persistence, system preference detection, next-intl setup for en/ur/+1, RTL support, locale-aware date formatting.  
**Deferred:** AI response language routing, per-conversation language preferences, extensive locale-specific layout changes.

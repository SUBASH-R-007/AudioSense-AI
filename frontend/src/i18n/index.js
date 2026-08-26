// Interface languages — distinct from the six counselling-sheet languages,
// which are backend content (languages.py) rather than UI chrome.
//
// Scope today is the Hearing Loss Simulator, the screen a patient is most
// likely to be looking at while a clinician talks them through their own
// loss. The structure is app-wide on purpose: add a namespace per page and a
// locale file per language, and nothing here changes.
//
// English is both the default and the fallback, so an untranslated key can
// never render as a bare key path in front of a patient.

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import simulatorEn from './locales/simulator.en.json'
import simulatorHi from './locales/simulator.hi.json'

//: localStorage, not sessionStorage like the case data: the language is a
//: clinic preference that should survive the browser tab, while patient state
//: deliberately dies with it.
const STORAGE_KEY = 'as_lang'

export const LANGUAGES = [
  { code: 'en', native: 'English' },
  { code: 'hi', native: 'हिन्दी' },
]

i18n.use(initReactI18next).init({
  resources: {
    en: { simulator: simulatorEn },
    hi: { simulator: simulatorHi },
  },
  lng: localStorage.getItem(STORAGE_KEY) || 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
})

export function setLanguage(code) {
  i18n.changeLanguage(code)
  try { localStorage.setItem(STORAGE_KEY, code) } catch { /* private mode */ }
}

export default i18n

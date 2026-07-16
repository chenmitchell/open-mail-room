import { createI18n } from 'vue-i18n'
import zhTW from '@/locales/zh-TW.json'
import en from '@/locales/en.json'

// 06-UI-UX.md §4: all copy lives in locale files; zh-TW is the default,
// adding a language = adding one more JSON file here.
export const i18n = createI18n({
  legacy: false,
  locale: 'zh-TW',
  fallbackLocale: 'en',
  messages: {
    'zh-TW': zhTW,
    en,
  },
})

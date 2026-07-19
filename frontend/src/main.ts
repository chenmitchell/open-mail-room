// Open Mail Room — self-hostable office mailroom system.
// Copyright (C) 2026 Mitchell Chen — https://github.com/chenmitchell
// SPDX-License-Identifier: AGPL-3.0-or-later WITH attribution term (see NOTICE)
// Upstream: https://github.com/chenmitchell/open-mail-room
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n } from './i18n'
import { registerAuthRedirect } from './stores/auth'
import './styles/tokens.css'
import './styles/base.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

// Wire the API client's 401 handler to a real navigation now that the
// router exists (see src/api/client.ts `onUnauthorized`).
registerAuthRedirect(() => {
  router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
})

app.mount('#app')

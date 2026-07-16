<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/AppButton.vue'

// In-app offline notice (reachable via Vue Router once the app shell has
// booted). Distinct from public/offline.html, which is the *service worker's*
// precached fallback for when the app shell itself can't load at all.
const { t } = useI18n({ useScope: 'global' })

function retry() {
  window.location.reload()
}
</script>

<template>
  <main class="offline-page">
    <div class="offline-page__card">
      <h1 class="offline-page__title">
        {{ t('offline.title') }}
      </h1>
      <p class="offline-page__message">
        {{ t('offline.message') }}
      </p>
      <AppButton @click="retry">
        {{ t('offline.retry') }}
      </AppButton>
    </div>
  </main>
</template>

<style scoped>
.offline-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  background-color: var(--color-bg);
}

.offline-page__card {
  max-width: 420px;
  text-align: center;
}

.offline-page__title {
  font-size: var(--font-size-2xl);
  margin-bottom: var(--space-3);
  color: var(--color-text);
}

.offline-page__message {
  color: var(--color-text-muted);
  margin-bottom: var(--space-5);
}
</style>

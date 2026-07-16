<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

// 06-UI-UX.md §2: "UI 顯示「離線,已排入佇列」與佇列數". Shown globally (see
// AppShell.vue) so the counter always knows whether captures are waiting to
// sync, not just while on the camera page.
const { t } = useI18n({ useScope: 'global' })
const store = useOfflineQueueStore()

const visible = computed(() => !store.isOnline || store.pendingCount > 0)
const message = computed(() =>
  !store.isOnline
    ? t('offlineQueue.offlineWithCount', { count: store.pendingCount })
    : t('offlineQueue.syncing', { count: store.pendingCount }),
)
</script>

<template>
  <p
    v-if="visible"
    class="offline-queue-badge"
    role="status"
    aria-live="polite"
  >
    <span
      class="offline-queue-badge__dot"
      aria-hidden="true"
    />
    {{ message }}
  </p>
</template>

<style scoped>
.offline-queue-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background-color: var(--oi-yellow);
  color: #000;
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.offline-queue-badge__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: var(--oi-vermillion);
  flex-shrink: 0;
}
</style>

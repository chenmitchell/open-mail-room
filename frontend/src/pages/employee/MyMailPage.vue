<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppBadge from '@/components/AppBadge.vue'
import AppButton from '@/components/AppButton.vue'
import HelpHint from '@/components/HelpHint.vue'
import { useAuthStore } from '@/stores/auth'
import { listMyItems } from '@/api/myItems'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { mailStatusBadgeVariant, mailStatusLabelKey } from '@/utils/mailStatus'
import type { MailItem, MailItemStatus } from '@/types/api'

// 06-UI-UX.md §1 「我的郵件」(employee): 自己的待領/歷史; 取件碼大字.
const { t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()

// 01 §3 狀態機: received/notified/unclaimed haven't been picked up yet.
const PENDING_STATUSES: MailItemStatus[] = ['received', 'notified', 'unclaimed']

const size = ref(20)
const items = ref<MailItem[]>([])
const total = ref(0)
// POLISH-AUDIT.md Should-fix #8: a single shared `loading` flag meant
// clicking "載入更多" (loadMore) flipped the whole page back into the
// top-level `v-else-if="loading"` branch, tearing down and re-mounting the
// already-rendered pending/history lists just to fetch 20 more rows.
// `initialLoading` gates the very first fetch (empty-state skeleton);
// `loadingMore` only drives the load-more button's own :loading spinner so
// the existing list stays mounted while more items are appended.
const initialLoading = ref(true)
const loadingMore = ref(false)
const loadError = ref<string | null>(null)

const pendingItems = computed(() => items.value.filter((i) => PENDING_STATUSES.includes(i.status)))
const historyItems = computed(() => items.value.filter((i) => !PENDING_STATUSES.includes(i.status)))
const hasMore = computed(() => items.value.length < total.value)

async function load(isLoadMore = false) {
  if (isLoadMore) {
    loadingMore.value = true
  } else {
    initialLoading.value = true
  }
  loadError.value = null
  try {
    const result = await listMyItems({ size: size.value })
    items.value = result.items
    total.value = result.meta.total
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    if (isLoadMore) {
      loadingMore.value = false
    } else {
      initialLoading.value = false
    }
  }
}

function loadMore() {
  size.value += 20
  load(true)
}

onMounted(() => load(false))
</script>

<template>
  <section class="my-mail-page">
    <h1 class="my-mail-page__title">
      {{ t('myMail.title') }}
      <HelpHint :text="t('help.hint.myMail')" />
    </h1>

    <div
      class="my-mail-page__code-card"
      aria-live="polite"
    >
      <p class="my-mail-page__code-label">
        {{ t('myMail.pickupCodeLabel') }}
      </p>
      <p
        v-if="auth.user?.pickup_code"
        class="my-mail-page__code-value"
      >
        {{ auth.user.pickup_code }}
      </p>
      <p
        v-else
        class="my-mail-page__code-missing"
      >
        {{ t('myMail.noPickupCode') }}
      </p>
      <p
        v-if="auth.user?.pickup_code"
        class="my-mail-page__code-hint"
      >
        {{ t('myMail.pickupCodeHint') }}
      </p>
    </div>

    <p
      v-if="loadError"
      class="my-mail-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p v-else-if="initialLoading">
      {{ t('common.loading') }}
    </p>

    <template v-else>
      <section class="my-mail-page__section">
        <h2 class="my-mail-page__section-title">
          {{ t('myMail.pendingTitle') }}
        </h2>
        <p
          v-if="pendingItems.length === 0"
          class="my-mail-page__empty"
        >
          {{ t('myMail.emptyPending') }}
        </p>
        <ul
          v-else
          class="my-mail-page__list"
        >
          <li
            v-for="item in pendingItems"
            :key="item.id"
            class="my-mail-page__item"
          >
            <span class="my-mail-page__item-main">
              <span class="my-mail-page__item-no">{{ item.item_no }}</span>
              <AppBadge
                :status="mailStatusBadgeVariant(item.status)"
                :label="t(mailStatusLabelKey(item.status))"
              />
            </span>
            <span class="my-mail-page__item-meta">
              <span v-if="item.sender_name">{{ t('myMail.colSender') }}: {{ item.sender_name }}</span>
              <span>{{ formatDateTime(item.received_at) }}</span>
            </span>
          </li>
        </ul>
      </section>

      <section class="my-mail-page__section">
        <h2 class="my-mail-page__section-title">
          {{ t('myMail.historyTitle') }}
        </h2>
        <p
          v-if="historyItems.length === 0"
          class="my-mail-page__empty"
        >
          {{ t('myMail.emptyHistory') }}
        </p>
        <ul
          v-else
          class="my-mail-page__list"
        >
          <li
            v-for="item in historyItems"
            :key="item.id"
            class="my-mail-page__item"
          >
            <span class="my-mail-page__item-main">
              <span class="my-mail-page__item-no">{{ item.item_no }}</span>
              <AppBadge
                :status="mailStatusBadgeVariant(item.status)"
                :label="t(mailStatusLabelKey(item.status))"
              />
            </span>
            <span class="my-mail-page__item-meta">
              <span>{{ t('myMail.colPickedUpAt') }}: {{ item.picked_up_at ? formatDateTime(item.picked_up_at) : '—' }}</span>
            </span>
          </li>
        </ul>
        <AppButton
          v-if="hasMore"
          variant="ghost"
          :loading="loadingMore"
          @click="loadMore"
        >
          {{ t('myMail.loadMore') }}
        </AppButton>
      </section>
    </template>
  </section>
</template>

<style scoped>
.my-mail-page {
  max-width: 640px;
}

.my-mail-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.my-mail-page__code-card {
  padding: var(--space-5);
  margin-bottom: var(--space-6);
  border: 2px solid var(--brand-primary);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  text-align: center;
}

.my-mail-page__code-label {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-muted);
}

.my-mail-page__code-value {
  margin: 0;
  font-size: 40px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--brand-primary);
}

.my-mail-page__code-missing {
  margin: 0;
  color: var(--color-text-muted);
}

.my-mail-page__code-hint {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.my-mail-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.my-mail-page__section {
  margin-bottom: var(--space-6);
}

.my-mail-page__section-title {
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.my-mail-page__empty {
  color: var(--color-text-muted);
  margin: 0;
}

.my-mail-page__list {
  list-style: none;
  margin: 0 0 var(--space-3);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  /* M8-2 badges spec "等寬對齊": same-width AppBadge across this list. */
  --app-badge-min-width: 112px;
}

.my-mail-page__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-height: var(--touch-target-min);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.my-mail-page__item-main {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.my-mail-page__item-no {
  font-weight: 700;
  color: var(--color-text);
}

.my-mail-page__item-meta {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}
</style>

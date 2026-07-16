<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/AppButton.vue'
import HelpHint from '@/components/HelpHint.vue'
import { listNotifications } from '@/api/notifications'
import { notifyItem } from '@/api/items'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import type { NotificationRecord } from '@/types/api'

// 06-UI-UX.md task brief 「通知失敗清單」(counter/admin): dead 通知列表 + 重發
// 按鈕. 05-NOTIFICATIONS.md §5: "失敗指數退避重試 5 次 -> dead 狀態進「通知
// 失敗」清單,櫃台可見並手動處理". Resend reuses the already-documented
// `POST /items/{id}/notify` (src/api/items.ts `notifyItem`); listing the
// dead queue itself is an ASSUMPTION — see src/api/notifications.ts.
const { t } = useI18n({ useScope: 'global' })

const records = ref<NotificationRecord[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const resending = reactive(new Set<string>())
const resendResults = reactive(new Map<string, { success: boolean; message: string }>())

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const result = await listNotifications({ status: 'dead', size: 100 })
    records.value = result.items
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

async function resend(record: NotificationRecord) {
  resending.add(record.id)
  resendResults.delete(record.id)
  try {
    await notifyItem(record.mail_item_id)
    // Deliberately not re-fetching the dead list here: a successful resend
    // would make this row disappear immediately (it's no longer `dead`),
    // wiping the "已重新發送通知" confirmation before the counter can see
    // it. Leave the row in place with its success message; the row clears
    // itself on the next manual/periodic refresh of the page.
    resendResults.set(record.id, { success: true, message: t('notificationFailures.resendSuccess') })
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('notificationFailures.resendError')
    resendResults.set(record.id, { success: false, message })
  } finally {
    resending.delete(record.id)
  }
}

function templateLabel(template: NotificationRecord['template']): string {
  return t(`notificationFailures.template.${template}`)
}

// POLISH-AUDIT.md Should-fix #10: the table used to print the raw
// NotificationChannel code (e.g. "line") straight from the API. Reuses the
// channel label set already maintained for notificationSettings.channel.*
// (see NotificationSettingsPage.vue's channelLabel()) rather than
// duplicating a second copy of the same channel-name translations.
function channelLabel(channel: NotificationRecord['channel']): string {
  return t(`notificationSettings.channel.${channel}`)
}

onMounted(load)
</script>

<template>
  <section class="notification-failures-page">
    <h1 class="notification-failures-page__title">
      {{ t('notificationFailures.title') }}
      <HelpHint :text="t('help.hint.notificationFailures')" />
    </h1>

    <p
      v-if="loadError"
      class="notification-failures-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p v-else-if="loading">
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="records.length === 0"
      class="notification-failures-page__empty"
    >
      {{ t('notificationFailures.empty') }}
    </p>

    <div
      v-else
      class="notification-failures-page__table-card"
    >
      <table class="notification-failures-page__table">
        <thead>
          <tr>
            <th scope="col">
              {{ t('notificationFailures.colItem') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colRecipient') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colChannel') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colTemplate') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colError') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colRetries') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colSentAt') }}
            </th>
            <th scope="col">
              {{ t('notificationFailures.colActions') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="record in records"
            :key="record.id"
          >
            <td :data-label="t('notificationFailures.colItem')">
              {{ record.item_no ?? record.mail_item_id }}
            </td>
            <td :data-label="t('notificationFailures.colRecipient')">
              {{ record.recipient_name ?? '—' }}
            </td>
            <td :data-label="t('notificationFailures.colChannel')">
              {{ channelLabel(record.channel) }}
            </td>
            <td :data-label="t('notificationFailures.colTemplate')">
              {{ templateLabel(record.template) }}
            </td>
            <td :data-label="t('notificationFailures.colError')">
              {{ record.error ?? '—' }}
            </td>
            <td :data-label="t('notificationFailures.colRetries')">
              {{ record.retries }}
            </td>
            <td :data-label="t('notificationFailures.colSentAt')">
              {{ record.sent_at ? formatDateTime(record.sent_at) : '—' }}
            </td>
            <td :data-label="t('notificationFailures.colActions')">
              <AppButton
                variant="secondary"
                :loading="resending.has(record.id)"
                @click="resend(record)"
              >
                {{ t('notificationFailures.resend') }}
              </AppButton>
              <p
                v-if="resendResults.has(record.id)"
                :class="resendResults.get(record.id)?.success
                  ? 'notification-failures-page__resend-ok'
                  : 'notification-failures-page__resend-fail'"
                role="status"
              >
                {{ resendResults.get(record.id)?.message }}
              </p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.notification-failures-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.notification-failures-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.notification-failures-page__empty {
  color: var(--color-text-muted);
}

.notification-failures-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.notification-failures-page__table {
  width: 100%;
  border-collapse: collapse;
}

.notification-failures-page__table th,
.notification-failures-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.notification-failures-page__resend-ok {
  color: var(--color-success-text);
  font-weight: 600;
  margin: var(--space-1) 0 0;
}

.notification-failures-page__resend-fail {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: var(--space-1) 0 0;
}

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640) -- same pattern
   as SearchPage.vue: <table>/<thead>/<td> semantics stay for assistive
   tech, but each row visually restyles as a card with data-label column
   names (POLISH-AUDIT.md Should-fix #5). */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .notification-failures-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .notification-failures-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .notification-failures-page__table,
  .notification-failures-page__table tbody,
  .notification-failures-page__table tr,
  .notification-failures-page__table td {
    display: block;
    width: 100%;
  }

  .notification-failures-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .notification-failures-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .notification-failures-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
    flex-shrink: 0;
  }
}
</style>

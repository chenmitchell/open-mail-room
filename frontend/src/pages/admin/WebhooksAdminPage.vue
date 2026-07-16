<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import { createWebhook, listWebhooks, testWebhook, updateWebhook } from '@/api/webhooks'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { WEBHOOK_EVENTS } from '@/types/api'
import type { WebhookEndpoint, WebhookTestResult } from '@/types/api'

// 06-UI-UX.md task brief 「admin webhooks 頁」: 列表/新增/停用/test(顯示結果).
// 03-API-SPEC.md §2 `GET|POST|PATCH /admin/webhooks`, `POST
// /admin/webhooks/{id}/test`; §3 event list + HMAC secret.
const { t } = useI18n({ useScope: 'global' })

const webhooks = ref<WebhookEndpoint[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const result = await listWebhooks()
    webhooks.value = result.items
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

// --- Create form -------------------------------------------------------
const form = reactive({
  name: '',
  url: '',
  events: [] as string[],
})
const nameError = ref<string | null>(null)
const urlError = ref<string | null>(null)
const eventsError = ref<string | null>(null)
const formError = ref<string | null>(null)
const saving = ref(false)

const revealedSecret = ref<string | null>(null)
const revealedName = ref<string | null>(null)

function resetForm() {
  form.name = ''
  form.url = ''
  form.events = []
  nameError.value = null
  urlError.value = null
  eventsError.value = null
  formError.value = null
}

function toggleEvent(event: string) {
  const idx = form.events.indexOf(event)
  if (idx === -1) {
    form.events.push(event)
  } else {
    form.events.splice(idx, 1)
  }
}

// POLISH-AUDIT.md Should-fix #11: both the subscription checkboxes and the
// table's "訂閱事件" column used to print the raw WEBHOOK_EVENTS code
// (e.g. "item.received") straight from the API/const.
function eventLabel(event: string): string {
  return t(`webhooksAdmin.event.${event}`)
}

async function onCreate() {
  formError.value = null
  nameError.value = form.name.trim() ? null : t('webhooksAdmin.errors.nameRequired')
  urlError.value = !form.url.trim()
    ? t('webhooksAdmin.errors.urlRequired')
    : !/^https:\/\//.test(form.url.trim())
      ? t('webhooksAdmin.errors.urlInvalid')
      : null
  eventsError.value = form.events.length ? null : t('webhooksAdmin.errors.eventsRequired')

  if (nameError.value || urlError.value || eventsError.value) return

  saving.value = true
  try {
    const created = await createWebhook({
      name: form.name.trim(),
      url: form.url.trim(),
      events: [...form.events],
    })
    revealedSecret.value = created.secret
    revealedName.value = created.name
    resetForm()
    await load()
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    saving.value = false
  }
}

function closeSecretReveal() {
  revealedSecret.value = null
  revealedName.value = null
}

// --- Activate / deactivate ----------------------------------------------
const toggling = reactive(new Set<string>())

async function toggleActive(webhook: WebhookEndpoint) {
  toggling.add(webhook.id)
  try {
    await updateWebhook(webhook.id, { is_active: !webhook.is_active })
    await load()
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    toggling.delete(webhook.id)
  }
}

// --- Test ------------------------------------------------------------
const testing = reactive(new Set<string>())
const testResults = reactive(new Map<string, WebhookTestResult>())

async function runTest(webhook: WebhookEndpoint) {
  testing.add(webhook.id)
  testResults.delete(webhook.id)
  try {
    const result = await testWebhook(webhook.id)
    testResults.set(webhook.id, result)
  } catch (err) {
    testResults.set(webhook.id, {
      success: false,
      message: err instanceof ApiError ? err.message : t('errors.generic'),
      sent_at: new Date().toISOString(),
    })
  } finally {
    testing.delete(webhook.id)
  }
}

onMounted(load)
</script>

<template>
  <section class="webhooks-admin-page">
    <h1 class="webhooks-admin-page__title">
      {{ t('webhooksAdmin.title') }}
    </h1>

    <form
      class="webhooks-admin-page__form"
      novalidate
      @submit.prevent="onCreate"
    >
      <h2 class="webhooks-admin-page__form-title">
        {{ t('webhooksAdmin.addNew') }}
      </h2>
      <AppInput
        v-model="form.name"
        :label="t('webhooksAdmin.nameLabel')"
        :error="nameError"
        required
      />
      <AppInput
        v-model="form.url"
        type="url"
        :label="t('webhooksAdmin.urlLabel')"
        :error="urlError"
        required
      />
      <fieldset class="webhooks-admin-page__events">
        <legend>{{ t('webhooksAdmin.eventsLabel') }}</legend>
        <label
          v-for="event in WEBHOOK_EVENTS"
          :key="event"
          class="webhooks-admin-page__event-option"
        >
          <input
            type="checkbox"
            :checked="form.events.includes(event)"
            @change="toggleEvent(event)"
          >
          {{ eventLabel(event) }}
        </label>
        <p
          v-if="eventsError"
          class="webhooks-admin-page__error"
          role="alert"
        >
          {{ eventsError }}
        </p>
      </fieldset>

      <p
        v-if="formError"
        class="webhooks-admin-page__error"
        role="alert"
      >
        {{ formError }}
      </p>

      <AppButton
        type="submit"
        :loading="saving"
      >
        {{ t('webhooksAdmin.save') }}
      </AppButton>
    </form>

    <p
      v-if="loadError"
      class="webhooks-admin-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p v-else-if="loading">
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="webhooks.length === 0"
      class="webhooks-admin-page__empty"
    >
      {{ t('webhooksAdmin.empty') }}
    </p>

    <table
      v-else
      class="webhooks-admin-page__table"
    >
      <thead>
        <tr>
          <th scope="col">
            {{ t('webhooksAdmin.colName') }}
          </th>
          <th scope="col">
            {{ t('webhooksAdmin.colUrl') }}
          </th>
          <th scope="col">
            {{ t('webhooksAdmin.colEvents') }}
          </th>
          <th scope="col">
            {{ t('webhooksAdmin.colStatus') }}
          </th>
          <th scope="col">
            {{ t('webhooksAdmin.colLastSuccess') }}
          </th>
          <th scope="col">
            {{ t('webhooksAdmin.colActions') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="webhook in webhooks"
          :key="webhook.id"
        >
          <td :data-label="t('webhooksAdmin.colName')">
            {{ webhook.name }}
          </td>
          <td :data-label="t('webhooksAdmin.colUrl')">
            {{ webhook.url }}
          </td>
          <td :data-label="t('webhooksAdmin.colEvents')">
            {{ webhook.events.map(eventLabel).join(', ') }}
          </td>
          <td :data-label="t('webhooksAdmin.colStatus')">
            {{ webhook.is_active ? t('webhooksAdmin.statusActive') : t('webhooksAdmin.statusInactive') }}
          </td>
          <td :data-label="t('webhooksAdmin.colLastSuccess')">
            <span>{{ webhook.last_success_at ? formatDateTime(webhook.last_success_at) : '—' }}</span>
            <span
              v-if="webhook.failure_count > 0"
              class="webhooks-admin-page__failure-count"
            >
              {{ t('webhooksAdmin.failureCount', { count: webhook.failure_count }) }}
            </span>
          </td>
          <td :data-label="t('webhooksAdmin.colActions')">
            <div class="webhooks-admin-page__actions">
              <AppButton
                variant="ghost"
                :loading="toggling.has(webhook.id)"
                @click="toggleActive(webhook)"
              >
                {{ webhook.is_active ? t('webhooksAdmin.toggleDeactivate') : t('webhooksAdmin.toggleActivate') }}
              </AppButton>
              <AppButton
                variant="secondary"
                :loading="testing.has(webhook.id)"
                @click="runTest(webhook)"
              >
                {{ t('webhooksAdmin.test') }}
              </AppButton>
            </div>
            <p
              v-if="testResults.has(webhook.id)"
              class="webhooks-admin-page__test-result"
              role="status"
            >
              <strong>{{ t('webhooksAdmin.testResultTitle') }}:</strong>
              <span v-if="testResults.get(webhook.id)?.success">
                {{ t('webhooksAdmin.testSuccess', { status: testResults.get(webhook.id)?.status_code ?? '' }) }}
              </span>
              <span
                v-else
                class="webhooks-admin-page__test-fail"
              >
                {{ t('webhooksAdmin.testFailure', { message: testResults.get(webhook.id)?.message ?? '' }) }}
              </span>
            </p>
          </td>
        </tr>
      </tbody>
    </table>

    <AppDialog
      :open="revealedSecret !== null"
      :title="t('webhooksAdmin.secretRevealTitle')"
      :close-on-backdrop="false"
      @close="closeSecretReveal"
    >
      <p>{{ t('webhooksAdmin.secretRevealMessage') }}</p>
      <p class="webhooks-admin-page__secret-name">
        {{ revealedName }}
      </p>
      <p class="webhooks-admin-page__secret-label">
        {{ t('webhooksAdmin.secretLabel') }}
      </p>
      <code class="webhooks-admin-page__secret-value">{{ revealedSecret }}</code>

      <template #footer>
        <AppButton @click="closeSecretReveal">
          {{ t('common.close') }}
        </AppButton>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.webhooks-admin-page__title {
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.webhooks-admin-page__form {
  max-width: 480px;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.webhooks-admin-page__form-title {
  font-size: var(--font-size-lg);
  margin: 0 0 var(--space-3);
}

.webhooks-admin-page__events {
  border: none;
  padding: 0;
  margin: 0 0 var(--space-4);
}

.webhooks-admin-page__events legend {
  font-weight: 600;
  padding: 0;
  margin-bottom: var(--space-2);
}

.webhooks-admin-page__event-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target-min);
}

.webhooks-admin-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.webhooks-admin-page__empty {
  color: var(--color-text-muted);
}

.webhooks-admin-page__table {
  width: 100%;
  border-collapse: collapse;
}

.webhooks-admin-page__table th,
.webhooks-admin-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.webhooks-admin-page__actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.webhooks-admin-page__test-result {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-sm);
}

.webhooks-admin-page__test-fail {
  color: var(--color-danger-text);
  font-weight: 600;
}

.webhooks-admin-page__failure-count {
  display: block;
  color: var(--color-danger-text);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.webhooks-admin-page__secret-name {
  font-weight: 700;
}

.webhooks-admin-page__secret-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: var(--space-3) 0 var(--space-1);
}

.webhooks-admin-page__secret-value {
  display: block;
  padding: var(--space-3);
  background-color: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  word-break: break-all;
  font-size: var(--font-size-sm);
}

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640) -- same pattern
   as SearchPage.vue (POLISH-AUDIT.md Should-fix #5). */
@media (max-width: 639px) {
  .webhooks-admin-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .webhooks-admin-page__table,
  .webhooks-admin-page__table tbody,
  .webhooks-admin-page__table tr,
  .webhooks-admin-page__table td {
    display: block;
    width: 100%;
  }

  .webhooks-admin-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .webhooks-admin-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .webhooks-admin-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
    flex-shrink: 0;
  }
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/AppSelect.vue'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import HelpHint from '@/components/HelpHint.vue'
import { getAiModels, getAiStatus, updateAiSettings } from '@/api/ai'
import { ApiError } from '@/api/client'
import type { AiStatus } from '@/types/api'

// task brief M9-FE 「AI 設定」管理頁: 對接已上線的 admin/ai 後端契約
// (GET /admin/ai/status, GET /admin/ai/models, PUT /admin/ai/settings).
const { t } = useI18n({ useScope: 'global' })

// --- Status ------------------------------------------------------------
const status = ref<AiStatus | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)

async function loadStatus() {
  loading.value = true
  loadError.value = null
  try {
    const result = await getAiStatus()
    status.value = result
    selectedModel.value = result.effective_model || ''
    dailyLimitInput.value = String(result.daily_request_limit)
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

// --- Model dropdown ------------------------------------------------------
const models = ref<string[]>([])
const modelsLoading = ref(false)
// AI_NO_KEY: no env key configured at all -- dropdown is disabled outright.
const modelsDisabled = ref(false)
// AI_MODELS_UNAVAILABLE (or any other ApiError): ListModels failed upstream
// -- shown as an error but the dropdown stays enabled (auto-detect still
// selectable, per task brief "允許手動維持自動").
const modelsError = ref<string | null>(null)
const selectedModel = ref('')

const modelOptions = computed(() => [
  { value: '', label: t('aiSettings.autoDetect') },
  ...models.value.map((m) => ({ value: m, label: m })),
])

const modelHint = computed(() => {
  if (modelsLoading.value) return t('common.loading')
  if (modelsDisabled.value) return t('aiSettings.noKeyWarning')
  return t('aiSettings.modelHint')
})

async function loadModels() {
  modelsLoading.value = true
  modelsDisabled.value = false
  modelsError.value = null
  try {
    const result = await getAiModels()
    models.value = result.models
  } catch (err) {
    if (err instanceof ApiError && err.code === 'AI_NO_KEY') {
      modelsDisabled.value = true
    } else if (err instanceof ApiError && err.code === 'AI_MODELS_UNAVAILABLE') {
      modelsError.value = err.message || t('aiSettings.modelsUnavailable')
    } else {
      modelsError.value = err instanceof ApiError ? err.message : t('errors.generic')
    }
  } finally {
    modelsLoading.value = false
  }
}

// --- Daily limit + save --------------------------------------------------
const dailyLimitInput = ref('10000')
const limitError = ref<string | null>(null)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)
const saving = ref(false)

// Contract: 1..100000 inclusive integer (03-API-SPEC.md admin/ai PUT body).
function validateLimit(): number | null {
  const raw = dailyLimitInput.value.trim()
  const n = Number(raw)
  if (raw === '' || !Number.isInteger(n) || n < 1 || n > 100000) {
    limitError.value = t('aiSettings.errors.limitRange')
    return null
  }
  limitError.value = null
  return n
}

async function onSave() {
  saveError.value = null
  saveSuccess.value = false
  const limit = validateLimit()
  if (limit === null) return

  saving.value = true
  try {
    const result = await updateAiSettings({
      // Empty string ("自動偵測") clears the DB override back to auto-detect.
      model: selectedModel.value === '' ? null : selectedModel.value,
      daily_request_limit: limit,
    })
    status.value = result
    selectedModel.value = result.effective_model || ''
    dailyLimitInput.value = String(result.daily_request_limit)
    saveSuccess.value = true
  } catch (err) {
    saveError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadStatus()
  loadModels()
})
</script>

<template>
  <section class="ai-settings-page">
    <h1 class="ai-settings-page__title">
      {{ t('aiSettings.title') }}
      <HelpHint :text="t('help.hint.aiSettings')" />
    </h1>

    <p v-if="loading">
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="loadError"
      class="ai-settings-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>

    <template v-else-if="status">
      <section
        class="ai-settings-page__status"
        aria-labelledby="ai-settings-status-heading"
      >
        <h2
          id="ai-settings-status-heading"
          class="ai-settings-page__section-title"
        >
          {{ t('aiSettings.statusTitle') }}
        </h2>
        <dl class="ai-settings-page__status-list">
          <div class="ai-settings-page__status-row">
            <dt>{{ t('aiSettings.keyLabel') }}</dt>
            <dd>{{ status.env_key_present ? t('aiSettings.keyPresent') : t('aiSettings.keyMissing') }}</dd>
          </div>
          <div class="ai-settings-page__status-row">
            <dt>{{ t('aiSettings.providerLabel') }}</dt>
            <dd>{{ status.provider }}</dd>
          </div>
          <div class="ai-settings-page__status-row">
            <dt>{{ t('aiSettings.usageLabel') }}</dt>
            <dd>{{ t('aiSettings.usageValue', { used: status.used_today, limit: status.daily_request_limit }) }}</dd>
          </div>
        </dl>
        <p
          v-if="!status.env_key_present"
          class="ai-settings-page__hint"
        >
          {{ t('aiSettings.keyMissingHint') }}
        </p>
      </section>

      <form
        class="ai-settings-page__form"
        novalidate
        @submit.prevent="onSave"
      >
        <h2 class="ai-settings-page__section-title">
          {{ t('aiSettings.formTitle') }}
        </h2>
        <AppSelect
          v-model="selectedModel"
          :label="t('aiSettings.modelLabel')"
          :hint="modelHint"
          :error="modelsError"
          :options="modelOptions"
          :disabled="modelsDisabled || modelsLoading"
        />
        <AppInput
          v-model="dailyLimitInput"
          type="number"
          :label="t('aiSettings.limitLabel')"
          :hint="t('aiSettings.limitHint')"
          :error="limitError"
          required
        />
        <p
          v-if="saveError"
          class="ai-settings-page__error"
          role="alert"
        >
          {{ saveError }}
        </p>
        <p
          v-if="saveSuccess"
          class="ai-settings-page__success"
          role="status"
        >
          {{ t('aiSettings.saveSuccess') }}
        </p>
        <AppButton
          type="submit"
          :loading="saving"
        >
          {{ t('aiSettings.save') }}
        </AppButton>
      </form>
    </template>
  </section>
</template>

<style scoped>
.ai-settings-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.ai-settings-page__section-title {
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.ai-settings-page__status {
  max-width: 480px;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.ai-settings-page__status-list {
  margin: 0;
}

.ai-settings-page__status-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
}

.ai-settings-page__status-row:last-child {
  border-bottom: none;
}

.ai-settings-page__status-row dt {
  font-weight: 600;
  color: var(--color-text-muted);
}

.ai-settings-page__status-row dd {
  margin: 0;
  color: var(--color-text);
  text-align: right;
}

.ai-settings-page__hint {
  margin: var(--space-3) 0 0;
  padding: var(--space-3);
  background-color: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.ai-settings-page__form {
  max-width: 480px;
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.ai-settings-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.ai-settings-page__success {
  color: var(--color-text);
  font-weight: 600;
}
</style>

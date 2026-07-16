<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/AppButton.vue'
import { pollBindingVerified } from '@/notifications/pollBinding'
import type {
  BindingStartResult,
  NotificationBinding,
  NotificationChannel,
  TelegramBindingStartResult,
} from '@/types/api'

// 05-NOTIFICATIONS.md §3 步驟 1-4: LINE/Telegram 綁定精靈, 06 §3 無障礙
// "綁定碼 aria-live". Shared by both channels since the state machine
// (idle -> starting -> waiting -> success/timeout/error, with cancel) is
// identical; only the start call, the deep-link button, and the step copy
// differ (see NotificationSettingsPage.vue for the two instantiations).
const props = defineProps<{
  channel: Extract<NotificationChannel, 'line' | 'telegram'>
  existingBindings: NotificationBinding[]
  startFn: () => Promise<BindingStartResult | TelegramBindingStartResult>
  fetchBindings: () => Promise<NotificationBinding[]>
}>()

const emit = defineEmits<{ bound: [binding: NotificationBinding] }>()

const { t } = useI18n({ useScope: 'global' })

type WizardState = 'idle' | 'starting' | 'waiting' | 'success' | 'timeout' | 'error'

const state = ref<WizardState>('idle')
const code = ref<string | null>(null)
const deepLink = ref<string | null>(null)
const expiresAt = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
let cancelled = false

const isTelegram = computed(() => props.channel === 'telegram')

const expiresInMinutes = computed(() => {
  if (!expiresAt.value) return null
  const ms = new Date(expiresAt.value).getTime() - Date.now()
  return Math.max(0, Math.ceil(ms / 60000))
})

async function start() {
  state.value = 'starting'
  errorMessage.value = null
  cancelled = false
  try {
    const result = await props.startFn()
    code.value = result.code
    expiresAt.value = result.expires_at
    deepLink.value = 'deep_link' in result ? result.deep_link : null
    state.value = 'waiting'

    const knownVerifiedIds = new Set(
      props.existingBindings.filter((b) => b.channel === props.channel && b.is_verified).map((b) => b.id),
    )

    const result2 = await pollBindingVerified(props.channel, props.fetchBindings, {
      knownVerifiedIds,
      isCancelled: () => cancelled,
    })

    if (result2.status === 'verified') {
      state.value = 'success'
      emit('bound', result2.binding)
    } else if (result2.status === 'timeout') {
      state.value = 'timeout'
    } else {
      state.value = 'idle'
    }
  } catch {
    state.value = 'error'
    errorMessage.value = t('notificationSettings.wizard.error')
  }
}

function cancel() {
  cancelled = true
  state.value = 'idle'
  code.value = null
}

function reset() {
  state.value = 'idle'
  code.value = null
}

onBeforeUnmount(() => {
  cancelled = true
})
</script>

<template>
  <div class="binding-code-wizard">
    <AppButton
      v-if="state === 'idle' || state === 'error'"
      variant="secondary"
      :loading="false"
      @click="start"
    >
      {{ isTelegram ? t('notificationSettings.wizard.telegramTitle') : t('notificationSettings.wizard.lineTitle') }}
    </AppButton>

    <p v-if="state === 'starting'">
      {{ t('common.loading') }}
    </p>

    <p
      v-if="state === 'error'"
      class="binding-code-wizard__error"
      role="alert"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="state === 'waiting'"
      class="binding-code-wizard__waiting"
    >
      <p>{{ isTelegram ? t('notificationSettings.wizard.step1Telegram') : t('notificationSettings.wizard.step1Line') }}</p>
      <p>{{ isTelegram ? t('notificationSettings.wizard.step2Telegram') : t('notificationSettings.wizard.step2Line') }}</p>

      <a
        v-if="isTelegram && deepLink"
        :href="deepLink"
        target="_blank"
        rel="noopener noreferrer"
        class="binding-code-wizard__deep-link"
      >
        {{ t('notificationSettings.wizard.openTelegram') }}
      </a>

      <p class="binding-code-wizard__code-label">
        {{ t('notificationSettings.wizard.codeLabel') }}
      </p>
      <p
        class="binding-code-wizard__code"
        aria-live="polite"
        role="status"
      >
        {{ code }}
      </p>
      <p
        v-if="expiresInMinutes !== null"
        class="binding-code-wizard__expires"
      >
        {{ t('notificationSettings.wizard.expiresIn', { minutes: expiresInMinutes }) }}
      </p>
      <p
        class="binding-code-wizard__polling"
        aria-live="polite"
      >
        {{ t('notificationSettings.wizard.waiting') }}
      </p>
      <AppButton
        variant="ghost"
        @click="cancel"
      >
        {{ t('notificationSettings.wizard.cancel') }}
      </AppButton>
    </div>

    <p
      v-if="state === 'success'"
      class="binding-code-wizard__success"
      role="status"
    >
      {{ t('notificationSettings.wizard.success') }}
    </p>

    <div v-if="state === 'timeout'">
      <p
        class="binding-code-wizard__error"
        role="alert"
      >
        {{ t('notificationSettings.wizard.timeout') }}
      </p>
      <AppButton
        variant="secondary"
        @click="reset"
      >
        {{ t('notificationSettings.wizard.retry') }}
      </AppButton>
    </div>
  </div>
</template>

<style scoped>
.binding-code-wizard {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-items: flex-start;
}

.binding-code-wizard__waiting {
  padding: var(--space-4);
  border: 2px solid var(--brand-primary);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  width: 100%;
}

.binding-code-wizard__deep-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--brand-primary);
  color: var(--brand-primary-contrast);
  font-weight: 600;
  text-decoration: none;
  margin-bottom: var(--space-3);
}

.binding-code-wizard__code-label {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-muted);
}

.binding-code-wizard__code {
  margin: 0;
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 0.2em;
  color: var(--brand-primary);
}

.binding-code-wizard__expires {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.binding-code-wizard__polling {
  margin: 0 0 var(--space-3);
  color: var(--color-text-muted);
}

.binding-code-wizard__success {
  color: var(--color-success-text);
  font-weight: 700;
}

.binding-code-wizard__error {
  color: var(--color-danger-text);
  font-weight: 600;
}
</style>

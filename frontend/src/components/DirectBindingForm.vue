<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import { createBinding } from '@/api/bindings'
import { ApiError } from '@/api/client'
import type { NotificationBinding, NotificationChannel } from '@/types/api'

// 05-NOTIFICATIONS.md §2 adapter table: email/slack/discord/webhook bind
// directly with an address/URL (no code wizard needed, unlike line/telegram
// — see BindingCodeWizard.vue). One reusable form component, parametrized by
// channel for the label/placeholder/validation.
const props = defineProps<{
  channel: Extract<NotificationChannel, 'email' | 'slack' | 'discord' | 'webhook'>
}>()

const emit = defineEmits<{ added: [binding: NotificationBinding] }>()

const { t } = useI18n({ useScope: 'global' })

const address = ref('')
const error = ref<string | null>(null)
const submitError = ref<string | null>(null)
const submitting = ref(false)

function validate(): boolean {
  const value = address.value.trim()
  if (!value) {
    error.value = t('notificationSettings.directForm.errors.addressRequired')
    return false
  }
  if (props.channel === 'email') {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailPattern.test(value)) {
      error.value = t('notificationSettings.directForm.errors.emailInvalid')
      return false
    }
  } else if (!/^https:\/\//.test(value)) {
    error.value = t('notificationSettings.directForm.errors.urlInvalid')
    return false
  }
  error.value = null
  return true
}

async function onSubmit() {
  submitError.value = null
  if (!validate()) return

  submitting.value = true
  try {
    const binding = await createBinding(props.channel, { address: address.value.trim() })
    address.value = ''
    emit('added', binding)
  } catch (err) {
    submitError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form
    class="direct-binding-form"
    novalidate
    @submit.prevent="onSubmit"
  >
    <AppInput
      v-model="address"
      :label="t(`notificationSettings.directForm.addressLabel.${channel}`)"
      :type="channel === 'email' ? 'email' : 'url'"
      :error="error"
      required
    />
    <p
      v-if="submitError"
      class="direct-binding-form__error"
      role="alert"
    >
      {{ submitError }}
    </p>
    <AppButton
      type="submit"
      variant="secondary"
      :loading="submitting"
    >
      {{ t('notificationSettings.directForm.submit') }}
    </AppButton>
  </form>
</template>

<style scoped>
.direct-binding-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
}

.direct-binding-form__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0;
}
</style>

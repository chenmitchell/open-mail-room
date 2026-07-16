<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import { changeMyPassword } from '@/api/users'
import { ApiError } from '@/api/client'

// M7-FE task brief: self-service password change, available to every
// authenticated role (not just admins) — entry point lives in AppShell.vue's
// nav. `POST /me/password` requires the current password;
// `CURRENT_PASSWORD_INVALID` (400) on mismatch, `WEAK_PASSWORD` (400) if the
// new password is under 10 characters.
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n({ useScope: 'global' })

const currentPassword = ref('')
const newPassword = ref('')
const currentPasswordError = ref<string | null>(null)
const newPasswordError = ref<string | null>(null)
const formError = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const saving = ref(false)

function resetForm() {
  currentPassword.value = ''
  newPassword.value = ''
  currentPasswordError.value = null
  newPasswordError.value = null
  formError.value = null
  successMessage.value = null
  saving.value = false
}

// The dialog stays mounted (AppShell renders it once, toggling `open`), so
// fields must be reset every time it's re-opened rather than only on create.
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) resetForm()
  },
)

async function onSubmit() {
  formError.value = null
  currentPasswordError.value = currentPassword.value ? null : t('changePassword.errors.currentPasswordRequired')
  newPasswordError.value =
    newPassword.value.length >= 10 ? null : t('changePassword.errors.passwordTooShort')
  if (currentPasswordError.value || newPasswordError.value) return

  saving.value = true
  try {
    await changeMyPassword({ current_password: currentPassword.value, new_password: newPassword.value })
    successMessage.value = t('changePassword.success')
  } catch (err) {
    if (err instanceof ApiError && err.code === 'CURRENT_PASSWORD_INVALID') {
      formError.value = t('changePassword.errors.currentPasswordInvalid')
    } else if (err instanceof ApiError && err.code === 'WEAK_PASSWORD') {
      formError.value = t('changePassword.errors.passwordTooShort')
    } else {
      formError.value = err instanceof ApiError ? err.message : t('errors.generic')
    }
  } finally {
    saving.value = false
  }
}

function onClose() {
  emit('close')
}
</script>

<template>
  <AppDialog
    :open="open"
    :title="t('changePassword.title')"
    @close="onClose"
  >
    <p
      v-if="successMessage"
      role="status"
      class="change-password-dialog__success"
    >
      {{ successMessage }}
    </p>
    <form
      v-else
      novalidate
      @submit.prevent="onSubmit"
    >
      <AppInput
        v-model="currentPassword"
        type="password"
        :label="t('changePassword.currentPasswordLabel')"
        :error="currentPasswordError"
        autocomplete="current-password"
        required
      />
      <AppInput
        v-model="newPassword"
        type="password"
        :label="t('changePassword.newPasswordLabel')"
        :hint="t('changePassword.passwordHint')"
        :error="newPasswordError"
        autocomplete="new-password"
        required
      />
      <p
        v-if="formError"
        role="alert"
        class="change-password-dialog__error"
      >
        {{ formError }}
      </p>
    </form>

    <template #footer>
      <template v-if="successMessage">
        <AppButton @click="onClose">
          {{ t('common.close') }}
        </AppButton>
      </template>
      <template v-else>
        <AppButton
          variant="ghost"
          type="button"
          @click="onClose"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          :loading="saving"
          @click="onSubmit"
        >
          {{ t('changePassword.submit') }}
        </AppButton>
      </template>
    </template>
  </AppDialog>
</template>

<style scoped>
.change-password-dialog__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0;
}

.change-password-dialog__success {
  color: var(--color-text);
  font-weight: 600;
  margin: 0;
}
</style>

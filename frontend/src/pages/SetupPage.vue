<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import { createInitialAdmin } from '@/api/setup'
import { markSetupComplete } from '@/router/setupStatus'
import { ApiError } from '@/api/client'

// SETUP-WIZARD: first-run "create the initial administrator" page
// (Gitea/Nextcloud-style first-visit setup). Reachable only while the
// backend reports `needs_setup: true` (src/router/index.ts's beforeEach
// guard) -- once an admin exists this route bounces to /login instead, so
// there is no need to re-check that here.
const MIN_PASSWORD_LENGTH = 10

const { t } = useI18n({ useScope: 'global' })
const router = useRouter()

const email = ref('')
const displayName = ref('')
const password = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const formError = ref<string | null>(null)

const passwordError = computed(() => {
  if (!password.value) return null
  if (password.value.length < MIN_PASSWORD_LENGTH) {
    return t('setup.errors.passwordTooShort', { min: MIN_PASSWORD_LENGTH })
  }
  return null
})

const confirmPasswordError = computed(() => {
  if (!confirmPassword.value) return null
  if (confirmPassword.value !== password.value) {
    return t('setup.errors.passwordMismatch')
  }
  return null
})

const canSubmit = computed(
  () =>
    email.value.trim().length > 0 &&
    displayName.value.trim().length > 0 &&
    password.value.length >= MIN_PASSWORD_LENGTH &&
    confirmPassword.value === password.value,
)

async function onSubmit() {
  formError.value = null

  if (password.value.length < MIN_PASSWORD_LENGTH) {
    formError.value = t('setup.errors.passwordTooShort', { min: MIN_PASSWORD_LENGTH })
    return
  }
  if (confirmPassword.value !== password.value) {
    formError.value = t('setup.errors.passwordMismatch')
    return
  }

  submitting.value = true
  try {
    await createInitialAdmin({
      email: email.value.trim(),
      display_name: displayName.value.trim(),
      password: password.value,
    })
    markSetupComplete()
    await router.replace({ name: 'login', query: { setup: 'done' } })
  } catch (err) {
    if (err instanceof ApiError && err.code === 'SETUP_ALREADY_DONE') {
      // Someone else finished the wizard first (race between two tabs, or
      // an ADMIN_EMAIL/ADMIN_PASSWORD-seeded admin appearing mid-flow) --
      // nothing left for this page to do but send the operator to /login.
      markSetupComplete()
      await router.replace({ name: 'login' })
      return
    }
    if (err instanceof ApiError && err.code === 'PASSWORD_TOO_WEAK') {
      formError.value = t('setup.errors.passwordTooShort', { min: MIN_PASSWORD_LENGTH })
    } else if (err instanceof ApiError && err.status === 429) {
      formError.value = t('errors.rateLimited')
    } else {
      formError.value = t('setup.submitError')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="setup-page">
    <form
      class="setup-page__card"
      novalidate
      @submit.prevent="onSubmit"
    >
      <div class="setup-page__brand">
        <svg
          class="setup-page__brand-mark"
          viewBox="0 0 32 32"
          aria-hidden="true"
          focusable="false"
        >
          <rect
            width="32"
            height="32"
            rx="7"
            class="setup-page__brand-mark-bg"
          />
          <rect
            x="6.5"
            y="9.5"
            width="19"
            height="14"
            rx="2"
            fill="none"
            stroke="#fff"
            stroke-width="1.6"
          />
          <path
            d="M6.5 11.5l9.5 6.5 9.5-6.5"
            fill="none"
            stroke="#fff"
            stroke-width="1.6"
            stroke-linejoin="round"
          />
        </svg>
      </div>
      <h1 class="setup-page__title">
        {{ $t('app.name') }}
      </h1>
      <p class="setup-page__subtitle">
        {{ $t('setup.title') }}
      </p>
      <p class="setup-page__intro">
        {{ $t('setup.intro') }}
      </p>

      <AppInput
        v-model="email"
        type="email"
        :label="$t('setup.email')"
        autocomplete="username"
        required
      />
      <AppInput
        v-model="displayName"
        type="text"
        :label="$t('setup.displayName')"
        autocomplete="name"
        required
      />
      <AppInput
        v-model="password"
        type="password"
        :label="$t('setup.password')"
        :hint="$t('setup.passwordHint', { min: MIN_PASSWORD_LENGTH })"
        :error="passwordError"
        autocomplete="new-password"
        required
      />
      <AppInput
        v-model="confirmPassword"
        type="password"
        :label="$t('setup.confirmPassword')"
        :error="confirmPasswordError"
        autocomplete="new-password"
        required
      />

      <p
        v-if="formError"
        class="setup-page__error"
        role="alert"
      >
        {{ formError }}
      </p>

      <AppButton
        type="submit"
        :loading="submitting"
        :disabled="!canSubmit"
        full-width
      >
        {{ $t('setup.submit') }}
      </AppButton>
    </form>
  </main>
</template>

<style scoped>
.setup-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  background-color: var(--color-bg);
}

.setup-page__card {
  width: 100%;
  max-width: 440px;
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background-color: var(--color-bg-elevated);
}

.setup-page__brand {
  display: flex;
  justify-content: center;
  margin: 0 0 var(--space-3);
}

.setup-page__brand-mark {
  width: 48px;
  height: 48px;
}

.setup-page__brand-mark-bg {
  fill: var(--brand-primary);
}

.setup-page__title {
  font-size: var(--font-size-2xl);
  margin: 0 0 var(--space-1);
  color: var(--color-text);
  text-align: center;
}

.setup-page__subtitle {
  margin: 0 0 var(--space-3);
  font-weight: 600;
  color: var(--color-text);
  text-align: center;
}

.setup-page__intro {
  margin: 0 0 var(--space-5);
  color: var(--color-text-muted);
  line-height: 1.6;
}

.setup-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}
</style>

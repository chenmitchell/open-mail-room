<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import { useAuthStore } from '@/stores/auth'
import AuthorCredit from '@/components/AuthorCredit.vue'
import { ApiError } from '@/api/client'

const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// M4-02 bug fix: this field previously sent `username`, but the backend
// (app/api/v1/auth.py `LoginRequest`) only ever accepted `{ email,
// password }` — renamed end-to-end (see stores/auth.ts `login`).
const email = ref('')
const password = ref('')
const submitting = ref(false)
const formError = ref<string | null>(null)

// SETUP-WIZARD: SetupPage.vue redirects here with `?setup=done` right after
// successfully creating the first administrator (src/router/index.ts's
// guard then keeps /setup unreachable from then on) -- this banner is the
// "管理員已建立,請登入" confirmation the operator needs before typing in
// the password they just chose.
const setupJustCompleted = computed(() => route.query.setup === 'done')

async function onSubmit() {
  formError.value = null
  submitting.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (err) {
    formError.value =
      err instanceof ApiError && err.status === 401 ? t('auth.loginError') : t('auth.loginGenericError')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <form
      class="login-page__card"
      novalidate
      @submit.prevent="onSubmit"
    >
      <div class="login-page__brand">
        <svg
          class="login-page__brand-mark"
          viewBox="0 0 32 32"
          aria-hidden="true"
          focusable="false"
        >
          <rect
            width="32"
            height="32"
            rx="7"
            class="login-page__brand-mark-bg"
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
      <h1 class="login-page__title">
        {{ $t('app.name') }}
      </h1>
      <p class="login-page__subtitle">
        {{ $t('auth.loginTitle') }}
      </p>

      <p
        v-if="setupJustCompleted"
        class="login-page__success"
        role="status"
      >
        {{ $t('setup.successRedirect') }}
      </p>

      <AppInput
        v-model="email"
        type="email"
        :label="$t('auth.email')"
        autocomplete="username"
        required
      />
      <AppInput
        v-model="password"
        type="password"
        :label="$t('auth.password')"
        autocomplete="current-password"
        required
      />

      <p
        v-if="formError"
        class="login-page__error"
        role="alert"
      >
        {{ formError }}
      </p>

      <AppButton
        type="submit"
        :loading="submitting"
        full-width
      >
        {{ $t('auth.loginSubmit') }}
      </AppButton>

      <p class="login-page__privacy">
        {{ $t('auth.privacyNotice') }}
      </p>
    </form>
    <AuthorCredit />
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  background-color: var(--color-bg);
}

.login-page__card {
  width: 100%;
  max-width: 400px;
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background-color: var(--color-bg-elevated);
}

.login-page__brand {
  display: flex;
  justify-content: center;
  margin: 0 0 var(--space-3);
}

.login-page__brand-mark {
  width: 48px;
  height: 48px;
}

.login-page__brand-mark-bg {
  fill: var(--brand-primary);
}

.login-page__title {
  font-size: var(--font-size-2xl);
  margin: 0 0 var(--space-1);
  color: var(--color-text);
  text-align: center;
}

.login-page__subtitle {
  margin: 0 0 var(--space-5);
  color: var(--color-text-muted);
  text-align: center;
}

.login-page__success {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-subtle);
  color: var(--color-text);
  font-weight: 600;
}

.login-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.login-page__privacy {
  margin-top: var(--space-5);
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-muted);
}
</style>

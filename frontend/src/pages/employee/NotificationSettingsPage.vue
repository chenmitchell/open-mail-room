<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppBadge from '@/components/AppBadge.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import BindingCodeWizard from '@/components/BindingCodeWizard.vue'
import DirectBindingForm from '@/components/DirectBindingForm.vue'
import HelpHint from '@/components/HelpHint.vue'
import { deleteBinding, listMyBindings, startLineBinding, startTelegramBinding } from '@/api/bindings'
import { ApiError } from '@/api/client'
import type { NotificationBinding, NotificationChannel } from '@/types/api'

// 06-UI-UX.md §1 「我的郵件」page's 通知設定; 03-API-SPEC.md §2 通知綁定;
// 05-NOTIFICATIONS.md §2/§3.
const { t } = useI18n({ useScope: 'global' })

const DIRECT_CHANNELS: Extract<NotificationChannel, 'email' | 'slack' | 'discord' | 'webhook'>[] = [
  'email',
  'slack',
  'discord',
  'webhook',
]

const bindings = ref<NotificationBinding[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    bindings.value = await listMyBindings()
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

function onBound() {
  load()
}

function onDirectAdded() {
  load()
}

function channelLabel(channel: NotificationChannel): string {
  return t(`notificationSettings.channel.${channel}`)
}

// --- Unbind confirmation ----------------------------------------------------
const unbindTarget = ref<NotificationBinding | null>(null)
const unbindError = ref<string | null>(null)
const unbinding = ref(false)

function openUnbindConfirm(binding: NotificationBinding) {
  unbindTarget.value = binding
  unbindError.value = null
}

function closeUnbindConfirm() {
  unbindTarget.value = null
}

async function confirmUnbind() {
  if (!unbindTarget.value) return
  unbinding.value = true
  unbindError.value = null
  try {
    await deleteBinding(unbindTarget.value.id)
    unbindTarget.value = null
    await load()
  } catch (err) {
    unbindError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    unbinding.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="notification-settings-page">
    <h1 class="notification-settings-page__title">
      {{ t('notificationSettings.title') }}
      <HelpHint :text="t('help.hint.notificationSettings')" />
    </h1>

    <section class="notification-settings-page__section">
      <h2 class="notification-settings-page__section-title">
        {{ t('notificationSettings.bindingsTitle') }}
      </h2>

      <p
        v-if="loadError"
        class="notification-settings-page__error"
        role="alert"
      >
        {{ loadError }}
      </p>
      <p v-else-if="loading">
        {{ t('common.loading') }}
      </p>
      <p
        v-else-if="bindings.length === 0"
        class="notification-settings-page__empty"
      >
        {{ t('notificationSettings.emptyBindings') }}
      </p>
      <ul
        v-else
        class="notification-settings-page__list"
      >
        <li
          v-for="binding in bindings"
          :key="binding.id"
          class="notification-settings-page__binding"
        >
          <span class="notification-settings-page__binding-main">
            <span class="notification-settings-page__binding-channel">{{ channelLabel(binding.channel) }}</span>
            <span class="notification-settings-page__binding-address">{{ binding.address }}</span>
            <AppBadge
              :status="binding.is_verified ? 'pickedUp' : 'pending'"
              :label="binding.is_verified ? t('notificationSettings.verified') : t('notificationSettings.unverified')"
            />
          </span>
          <button
            type="button"
            class="notification-settings-page__unbind-btn"
            @click="openUnbindConfirm(binding)"
          >
            {{ t('notificationSettings.unbind') }}
          </button>
        </li>
      </ul>
    </section>

    <section class="notification-settings-page__section">
      <h2 class="notification-settings-page__section-title">
        {{ t('notificationSettings.wizard.lineTitle') }}
      </h2>
      <BindingCodeWizard
        channel="line"
        :existing-bindings="bindings"
        :start-fn="startLineBinding"
        :fetch-bindings="listMyBindings"
        @bound="onBound"
      />
    </section>

    <section class="notification-settings-page__section">
      <h2 class="notification-settings-page__section-title">
        {{ t('notificationSettings.wizard.telegramTitle') }}
      </h2>
      <BindingCodeWizard
        channel="telegram"
        :existing-bindings="bindings"
        :start-fn="startTelegramBinding"
        :fetch-bindings="listMyBindings"
        @bound="onBound"
      />
    </section>

    <section
      v-for="channel in DIRECT_CHANNELS"
      :key="channel"
      class="notification-settings-page__section"
    >
      <h2 class="notification-settings-page__section-title">
        {{ channelLabel(channel) }}
      </h2>
      <DirectBindingForm
        :channel="channel"
        @added="onDirectAdded"
      />
    </section>

    <AppDialog
      :open="unbindTarget !== null"
      :title="t('notificationSettings.unbindConfirmTitle')"
      @close="closeUnbindConfirm"
    >
      <p v-if="unbindTarget">
        {{ t('notificationSettings.unbindConfirmMessage', { channel: channelLabel(unbindTarget.channel) }) }}
      </p>
      <p
        v-if="unbindError"
        class="notification-settings-page__error"
        role="alert"
      >
        {{ unbindError }}
      </p>

      <template #footer>
        <AppButton
          variant="ghost"
          type="button"
          @click="closeUnbindConfirm"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          variant="danger"
          :loading="unbinding"
          @click="confirmUnbind"
        >
          {{ t('notificationSettings.unbind') }}
        </AppButton>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.notification-settings-page {
  max-width: 640px;
}

.notification-settings-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.notification-settings-page__section {
  margin-bottom: var(--space-6);
  padding-bottom: var(--space-5);
  border-bottom: 1px solid var(--color-border);
}

.notification-settings-page__section-title {
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.notification-settings-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.notification-settings-page__empty {
  color: var(--color-text-muted);
  margin: 0;
}

.notification-settings-page__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  /* M8-2 badges spec "等寬對齊": same-width AppBadge across this list. */
  --app-badge-min-width: 100px;
}

.notification-settings-page__binding {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  min-height: var(--touch-target-min);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.notification-settings-page__binding-main {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.notification-settings-page__binding-channel {
  font-weight: 700;
  color: var(--color-text);
}

.notification-settings-page__binding-address {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.notification-settings-page__unbind-btn {
  min-height: var(--touch-target-min);
  min-width: var(--touch-target-min);
  padding: var(--space-1) var(--space-3);
  border: 2px solid var(--oi-vermillion);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-danger-text);
  font-weight: 600;
  cursor: pointer;
}
</style>

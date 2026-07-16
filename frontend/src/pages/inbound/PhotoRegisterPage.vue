<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppButton from '@/components/AppButton.vue'
import CameraCapture from '@/components/CameraCapture.vue'
import HelpHint from '@/components/HelpHint.vue'
import { useOfflineQueueStore } from '@/stores/offlineQueue'
import { useObjectUrlCache } from '@/composables/useObjectUrlCache'
import { scanBarcodeFromBlob } from '@/barcode/scan'
import {
  addAsNewGroup,
  addToLastGroup,
  groupPhotos,
  removePhoto,
  type CapturedPhoto,
} from './photoGroups'
import { useSubmitPhotoGroups } from './useSubmitPhotoGroups'

// 06-UI-UX.md §1/§2: 拍照登記頁 — 相機即時預覽 + ZXing 即時掃碼框、連拍模式
// (一張=一件)、「＋加拍同件」、照片預覽/重拍/刪除.
const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const offlineQueue = useOfflineQueueStore()
const { submit } = useSubmitPhotoGroups()

const cameraRef = ref<InstanceType<typeof CameraCapture> | null>(null)
const photos = ref<CapturedPhoto[]>([])
const nextCaptureMode = ref<'new' | 'same'>('new')
const submitting = ref(false)
const submitError = ref<string | null>(null)
const submitMessage = ref<string | null>(null)

const groups = computed(() => groupPhotos(photos.value))
const hasPhotos = computed(() => photos.value.length > 0)

// HEIC/HEIF from a phone camera (via the file-input fallback) can't be
// decoded by the browser for a local <img> preview even though the backend
// now transcodes it to JPEG on upload -- so the preview <img> fails to load.
// Track those and show a text placeholder instead of a broken-image icon.
const previewErrors = reactive<Record<string, boolean>>({})
function onPreviewError(photoId: string) {
  previewErrors[photoId] = true
}

// POLISH-AUDIT.md Nice #15: cached + auto-revoked per-photo object URLs
// instead of minting a fresh, never-revoked one on every re-render.
const { getUrl } = useObjectUrlCache(photos)

function captureNewItem() {
  nextCaptureMode.value = 'new'
  cameraRef.value?.capturePhoto()
}

function captureSameItem() {
  nextCaptureMode.value = 'same'
  cameraRef.value?.capturePhoto()
}

async function onCapture(payload: { blob: Blob; filename: string }) {
  photos.value =
    nextCaptureMode.value === 'same' && photos.value.length > 0
      ? addToLastGroup(photos.value, payload.blob, payload.filename)
      : addAsNewGroup(photos.value, payload.blob, payload.filename)

  const captured = photos.value[photos.value.length - 1]
  // 04 §1: barcode scan runs per photo, result attaches as `barcode_hint`.
  const hint = await scanBarcodeFromBlob(payload.blob)
  if (hint) {
    photos.value = photos.value.map((p) => (p.id === captured.id ? { ...p, barcodeHint: hint.value } : p))
  }
}

function onRetake(photoId: string) {
  photos.value = removePhoto(photos.value, photoId)
}

async function onSubmit() {
  submitError.value = null
  submitMessage.value = null
  submitting.value = true
  try {
    const result = await submit(photos.value)
    if (result.queued > 0) {
      submitMessage.value = t('inbound.camera.queuedOffline', { count: result.queued })
      await offlineQueue.refreshCount()
    } else {
      submitMessage.value = t('inbound.camera.jobsCreated', { count: result.jobs })
      router.push({ name: 'inbound-confirm' })
      return
    }
    photos.value = []
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="photo-register-page">
    <h1 class="photo-register-page__title">
      {{ t('inbound.camera.title') }}
      <HelpHint :text="t('help.hint.photoRegister')" />
    </h1>

    <p
      v-if="!offlineQueue.isOnline"
      class="photo-register-page__offline-banner"
      role="status"
    >
      {{ t('inbound.camera.offlineBanner') }}
    </p>

    <CameraCapture
      ref="cameraRef"
      @capture="onCapture"
    />

    <div class="photo-register-page__actions">
      <AppButton
        variant="primary"
        @click="captureNewItem"
      >
        {{ t('inbound.camera.captureNew') }}
      </AppButton>
      <AppButton
        variant="secondary"
        :disabled="!hasPhotos"
        @click="captureSameItem"
      >
        {{ t('inbound.camera.captureSame') }}
      </AppButton>
    </div>

    <p class="photo-register-page__hint">
      {{ t('inbound.camera.frontBackHint') }}
    </p>

    <ul
      v-if="hasPhotos"
      class="photo-register-page__groups"
      :aria-label="t('inbound.camera.groupListLabel')"
    >
      <li
        v-for="(group, index) in groups"
        :key="group[0].groupId"
        class="photo-register-page__group"
      >
        <h2 class="photo-register-page__group-title">
          {{ t('inbound.camera.groupLabel', { n: index + 1 }) }}
        </h2>
        <ul class="photo-register-page__thumbs">
          <li
            v-for="photo in group"
            :key="photo.id"
            class="photo-register-page__thumb"
          >
            <img
              v-if="!previewErrors[photo.id]"
              :src="getUrl(photo.id)"
              :alt="t('inbound.camera.photoAlt')"
              class="photo-register-page__thumb-img"
              @error="onPreviewError(photo.id)"
            >
            <p
              v-else
              class="photo-register-page__thumb-fallback"
              role="status"
            >
              {{ t('inbound.camera.previewUnsupported') }}
            </p>
            <p
              v-if="photo.barcodeHint"
              class="photo-register-page__barcode"
              aria-live="polite"
            >
              {{ t('inbound.camera.barcodeDetected', { value: photo.barcodeHint }) }}
            </p>
            <AppButton
              variant="ghost"
              @click="onRetake(photo.id)"
            >
              {{ t('inbound.camera.retake') }}
            </AppButton>
          </li>
        </ul>
      </li>
    </ul>

    <p
      v-if="submitMessage"
      class="photo-register-page__message"
      role="status"
    >
      {{ submitMessage }}
    </p>
    <p
      v-if="submitError"
      class="photo-register-page__error"
      role="alert"
    >
      {{ submitError }}
    </p>

    <AppButton
      variant="primary"
      full-width
      :loading="submitting"
      :disabled="!hasPhotos"
      @click="onSubmit"
    >
      {{ t('inbound.camera.submit') }}
    </AppButton>
  </section>
</template>

<style scoped>
.photo-register-page {
  max-width: 640px;
}

.photo-register-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.photo-register-page__offline-banner {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--oi-yellow);
  color: #000;
  font-weight: 600;
}

.photo-register-page__actions {
  display: flex;
  gap: var(--space-3);
  margin: var(--space-4) 0;
}

.photo-register-page__groups {
  list-style: none;
  margin: 0 0 var(--space-4);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.photo-register-page__group {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.photo-register-page__group-title {
  font-size: var(--font-size-base);
  margin: 0 0 var(--space-2);
  color: var(--color-text);
}

.photo-register-page__thumbs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.photo-register-page__thumb {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 140px;
}

.photo-register-page__thumb-img {
  width: 140px;
  height: 105px;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.photo-register-page__thumb-fallback {
  width: 140px;
  min-height: 105px;
  margin: 0;
  padding: var(--space-2);
  display: flex;
  align-items: center;
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-border);
  background-color: var(--color-bg-subtle);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.photo-register-page__barcode {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-success-text);
  font-weight: 600;
}

.photo-register-page__message {
  margin: 0 0 var(--space-3);
  color: var(--color-success-text);
  font-weight: 600;
}

.photo-register-page__error {
  margin: 0 0 var(--space-3);
  color: var(--color-danger-text);
  font-weight: 600;
}
.photo-register-page__hint {
  margin: var(--space-2) 0 var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}
</style>

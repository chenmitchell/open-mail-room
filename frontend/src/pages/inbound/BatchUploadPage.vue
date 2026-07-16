<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppButton from '@/components/AppButton.vue'
import HelpHint from '@/components/HelpHint.vue'
import { uploadPhotos, MAX_BATCH_SIZE } from '@/api/uploads'
import { createOcrJob } from '@/api/ocr'
import { scanBarcodeFromBlob } from '@/barcode/scan'
import { useOfflineQueueStore } from '@/stores/offlineQueue'
import { useOcrConfirmQueueStore } from '@/stores/ocrConfirmQueue'
import { useObjectUrlCache } from '@/composables/useObjectUrlCache'
import {
  addAsNewGroup,
  buildBarcodeHints,
  buildOcrJobPayloads,
  groupBarcodeHint,
  groupPhotos,
  mergeIntoGroup,
  removePhoto,
  type CapturedPhoto,
} from './photoGroups'
import { useSubmitPhotoGroups } from './useSubmitPhotoGroups'

// 06-UI-UX.md §1: 批次上傳頁 — 多選 <=30 張、逐張進度、失敗重試;確認頁可
// 框選多張合併為一件.
const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const offlineQueue = useOfflineQueueStore()
const confirmQueue = useOcrConfirmQueueStore()
const { submit: submitOffline } = useSubmitPhotoGroups()

type PhotoUploadStatus = 'pending' | 'uploading' | 'uploaded' | 'failed'
interface PhotoUploadState {
  status: PhotoUploadStatus
  progress: number
  error: string | null
  attachmentId: string | null
}

const photos = ref<CapturedPhoto[]>([])
const uploadStates = reactive<Record<string, PhotoUploadState>>({})
// attachment id -> EXIF capture time (UTC ISO) or null, handed to the confirm
// page so each photo can show when it was actually taken.
const capturedAtByAttachmentId = reactive<Record<string, string | null>>({})
const selected = ref<Set<string>>(new Set())
const fileInputRef = ref<HTMLInputElement | null>(null)

const submitting = ref(false)
const submitError = ref<string | null>(null)
const submitMessage = ref<string | null>(null)

const groups = computed(() => groupPhotos(photos.value))
const hasPhotos = computed(() => photos.value.length > 0)
const allUploaded = computed(
  () => hasPhotos.value && photos.value.every((p) => uploadStates[p.id]?.status === 'uploaded'),
)
const hasFailed = computed(() => photos.value.some((p) => uploadStates[p.id]?.status === 'failed'))

// POLISH-AUDIT.md Nice #15: cached + auto-revoked per-photo object URLs
// instead of minting a fresh, never-revoked one on every re-render (used for
// the *local* upload-progress thumbnails on this page only). FE-STABILITY:
// the confirm-queue hand-off in `onCreateJobs` below used to also mint a
// throwaway `URL.createObjectURL` per photo for OcrConfirmPage's left-side
// preview -- that one is gone now that OcrConfirmPage loads photos from
// `GET /api/v1/uploads/{attachment_id}` via `attachmentIds` instead, so
// there's nothing left for this page to hand off or for that page to revoke.
const { getUrl } = useObjectUrlCache(photos)

// HEIC/HEIF picked from the gallery can't be decoded by the browser for a
// local <img> preview (it still uploads + OCRs fine via backend transcode),
// so show a text placeholder instead of a broken-image icon.
const previewErrors = reactive<Record<string, boolean>>({})
function onPreviewError(photoId: string) {
  previewErrors[photoId] = true
}

function openFilePicker() {
  fileInputRef.value?.click()
}

function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (files.length === 0) return
  if (photos.value.length + files.length > MAX_BATCH_SIZE) {
    submitError.value = t('inbound.batch.tooMany', { max: MAX_BATCH_SIZE })
    return
  }
  submitError.value = null
  for (const file of files) {
    photos.value = addAsNewGroup(photos.value, file, file.name)
    const added = photos.value[photos.value.length - 1]
    uploadStates[added.id] = { status: 'pending', progress: 0, error: null, attachmentId: null }
    void scanBarcodeFromBlob(file).then((hint) => {
      if (hint) {
        photos.value = photos.value.map((p) => (p.id === added.id ? { ...p, barcodeHint: hint.value } : p))
      }
    })
  }
}

function toggleSelect(id: string) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function mergeSelected() {
  if (selected.value.size < 2) return
  photos.value = mergeIntoGroup(photos.value, [...selected.value])
  selected.value = new Set()
}

function onRemove(id: string) {
  photos.value = removePhoto(photos.value, id)
  delete uploadStates[id]
  const next = new Set(selected.value)
  next.delete(id)
  selected.value = next
}

async function uploadTargets(targets: CapturedPhoto[]) {
  if (targets.length === 0) return
  for (const p of targets) {
    uploadStates[p.id] = { status: 'uploading', progress: 0, error: null, attachmentId: null }
  }
  const { attachmentIds, capturedAt, failures } = await uploadPhotos(
    targets.map((p) => ({ localId: p.id, blob: p.blob, filename: p.filename })),
    (localId, fraction) => {
      if (uploadStates[localId]) uploadStates[localId].progress = fraction
    },
  )
  for (const [localId, attachmentId] of Object.entries(attachmentIds)) {
    uploadStates[localId] = { status: 'uploaded', progress: 1, error: null, attachmentId }
  }
  Object.assign(capturedAtByAttachmentId, capturedAt)
  for (const [localId, err] of Object.entries(failures)) {
    uploadStates[localId] = { status: 'failed', progress: 0, error: err.message, attachmentId: null }
  }
}

async function onUploadAll() {
  submitError.value = null
  submitMessage.value = null

  if (!offlineQueue.isOnline) {
    submitting.value = true
    try {
      const result = await submitOffline(photos.value)
      submitMessage.value = t('inbound.batch.queuedOffline', { count: result.queued })
      photos.value = []
    } catch (err) {
      submitError.value = err instanceof Error ? err.message : t('errors.generic')
    } finally {
      submitting.value = false
    }
    return
  }

  submitting.value = true
  try {
    const targets = photos.value.filter((p) => uploadStates[p.id]?.status !== 'uploaded')
    await uploadTargets(targets)
  } finally {
    submitting.value = false
  }
}

async function onRetryFailed() {
  const targets = photos.value.filter((p) => uploadStates[p.id]?.status === 'failed')
  submitting.value = true
  try {
    await uploadTargets(targets)
  } finally {
    submitting.value = false
  }
}

async function onCreateJobs() {
  submitError.value = null
  submitting.value = true
  try {
    const attachmentIdByPhotoId: Record<string, string> = {}
    for (const p of photos.value) {
      const id = uploadStates[p.id]?.attachmentId
      if (id) attachmentIdByPhotoId[p.id] = id
    }
    const payloads = buildOcrJobPayloads(photos.value, attachmentIdByPhotoId)
    for (const payload of payloads) {
      const group = groups.value.find((g) => g[0].groupId === payload.groupId)
      if (!group) continue
      const job = await createOcrJob(
        payload.attachment_ids,
        buildBarcodeHints(group, attachmentIdByPhotoId),
      )
      confirmQueue.push({
        jobId: job.id,
        attachmentIds: payload.attachment_ids,
        barcodeHint: groupBarcodeHint(group).value,
        capturedAt: { ...capturedAtByAttachmentId },
      })
    }
    router.push({ name: 'inbound-confirm' })
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="batch-upload-page">
    <h1 class="batch-upload-page__title">
      {{ t('inbound.batch.title') }}
      <HelpHint :text="t('help.hint.batchUpload')" />
    </h1>

    <p
      v-if="!offlineQueue.isOnline"
      class="batch-upload-page__offline-banner"
      role="status"
    >
      {{ t('inbound.camera.offlineBanner') }}
    </p>

    <AppButton
      variant="primary"
      @click="openFilePicker"
    >
      {{ t('inbound.batch.selectFiles') }}
    </AppButton>
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      multiple
      class="batch-upload-page__file-input"
      :aria-label="t('inbound.batch.selectFiles')"
      @change="onFilesSelected"
    >

    <p
      v-if="submitError"
      class="batch-upload-page__error"
      role="alert"
    >
      {{ submitError }}
    </p>
    <p
      v-if="submitMessage"
      class="batch-upload-page__message"
      role="status"
    >
      {{ submitMessage }}
    </p>

    <template v-if="hasPhotos">
      <div class="batch-upload-page__toolbar">
        <AppButton
          variant="secondary"
          :disabled="selected.size < 2"
          @click="mergeSelected"
        >
          {{ t('inbound.batch.mergeSelected', { count: selected.size }) }}
        </AppButton>
      </div>

      <ul
        class="batch-upload-page__groups"
        :aria-label="t('inbound.camera.groupListLabel')"
      >
        <li
          v-for="(group, index) in groups"
          :key="group[0].groupId"
          class="batch-upload-page__group"
        >
          <h2 class="batch-upload-page__group-title">
            {{ t('inbound.camera.groupLabel', { n: index + 1 }) }}
          </h2>
          <ul class="batch-upload-page__thumbs">
            <li
              v-for="photo in group"
              :key="photo.id"
              class="batch-upload-page__thumb"
            >
              <label class="batch-upload-page__select">
                <input
                  type="checkbox"
                  :checked="selected.has(photo.id)"
                  @change="toggleSelect(photo.id)"
                >
                {{ t('inbound.batch.selectForMerge') }}
              </label>
              <img
                v-if="!previewErrors[photo.id]"
                :src="getUrl(photo.id)"
                :alt="t('inbound.camera.photoAlt')"
                class="batch-upload-page__thumb-img"
                @error="onPreviewError(photo.id)"
              >
              <p
                v-else
                class="batch-upload-page__thumb-fallback"
                role="status"
              >
                {{ t('inbound.camera.previewUnsupported') }}
              </p>
              <p
                v-if="photo.barcodeHint"
                class="batch-upload-page__barcode"
                aria-live="polite"
              >
                {{ t('inbound.camera.barcodeDetected', { value: photo.barcodeHint }) }}
              </p>
              <p
                class="batch-upload-page__status"
                role="status"
              >
                {{ t(`inbound.batch.status.${uploadStates[photo.id]?.status ?? 'pending'}`) }}
                <span v-if="uploadStates[photo.id]?.status === 'uploading'">
                  {{ Math.round((uploadStates[photo.id]?.progress ?? 0) * 100) }}%
                </span>
              </p>
              <p
                v-if="uploadStates[photo.id]?.error"
                class="batch-upload-page__thumb-error"
                role="alert"
              >
                {{ uploadStates[photo.id]?.error }}
              </p>
              <AppButton
                variant="ghost"
                @click="onRemove(photo.id)"
              >
                {{ t('inbound.batch.remove') }}
              </AppButton>
            </li>
          </ul>
        </li>
      </ul>

      <div class="batch-upload-page__submit-row">
        <AppButton
          variant="primary"
          :loading="submitting"
          @click="onUploadAll"
        >
          {{ t('inbound.batch.uploadAll') }}
        </AppButton>
        <AppButton
          v-if="hasFailed"
          variant="secondary"
          :loading="submitting"
          @click="onRetryFailed"
        >
          {{ t('inbound.batch.retryFailed') }}
        </AppButton>
        <AppButton
          variant="primary"
          :disabled="!allUploaded"
          :loading="submitting"
          @click="onCreateJobs"
        >
          {{ t('inbound.batch.createJobs') }}
        </AppButton>
      </div>
    </template>
  </section>
</template>

<style scoped>
.batch-upload-page {
  max-width: 720px;
}

.batch-upload-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.batch-upload-page__offline-banner {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--oi-yellow);
  color: #000;
  font-weight: 600;
}

.batch-upload-page__file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.batch-upload-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: var(--space-3) 0;
}

.batch-upload-page__message {
  color: var(--color-success-text);
  font-weight: 600;
  margin: var(--space-3) 0;
}

.batch-upload-page__toolbar {
  margin: var(--space-4) 0;
}

.batch-upload-page__groups {
  list-style: none;
  margin: 0 0 var(--space-4);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.batch-upload-page__group {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.batch-upload-page__group-title {
  font-size: var(--font-size-base);
  margin: 0 0 var(--space-2);
  color: var(--color-text);
}

.batch-upload-page__thumbs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.batch-upload-page__thumb {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 160px;
}

.batch-upload-page__select {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-height: var(--touch-target-min);
  font-size: var(--font-size-xs);
}

.batch-upload-page__thumb-img {
  width: 160px;
  height: 120px;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.batch-upload-page__thumb-fallback {
  width: 160px;
  min-height: 120px;
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

.batch-upload-page__barcode {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-success-text);
  font-weight: 600;
}

.batch-upload-page__status {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.batch-upload-page__thumb-error {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-danger-text);
  font-weight: 600;
}

.batch-upload-page__submit-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
</style>

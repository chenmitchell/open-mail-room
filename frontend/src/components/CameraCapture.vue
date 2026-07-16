<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { startLiveScan, type LiveScanControls } from '@/barcode/scan'
import type { BarcodeHint } from '@/types/api'

// 06-UI-UX.md §2: "相機:<input type=file capture=environment> 為基準
// (iOS/Android 皆穩);進階即時掃碼用 getUserMedia...兩者都做,getUserMedia
// 不可用時自動降級". This component owns ONLY the capture mechanism (live
// preview vs. file-input fallback) and the live scan overlay; it has no
// opinion on grouping ("一張=一件" vs "＋加拍同件") — that's the caller's
// job (see PhotoRegisterPage.vue / src/pages/inbound/photoGroups.ts), since
// the grouping choice is made by which button the counter presses, not by
// anything the camera itself knows.
const emit = defineEmits<{
  capture: [payload: { blob: Blob; filename: string }]
  liveBarcode: [hint: BarcodeHint]
}>()

const { t } = useI18n({ useScope: 'global' })

const videoRef = ref<HTMLVideoElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const liveModeActive = ref(false)
const cameraError = ref<string | null>(null)
const lastDetectedBarcode = ref<string | null>(null)

let stream: MediaStream | null = null
let scanControls: LiveScanControls | null = null

async function startLive(): Promise<void> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    liveModeActive.value = false
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    const video = videoRef.value
    if (!video) throw new Error('camera-capture: video element not mounted')
    video.srcObject = stream
    await video.play()
    liveModeActive.value = true
    cameraError.value = null
    scanControls = await startLiveScan(video, (hint) => {
      lastDetectedBarcode.value = hint.value
      emit('liveBarcode', hint)
    })
  } catch {
    // Permission denied, no camera, insecure context, unsupported browser...
    // all degrade silently to the file-input baseline (06 §2).
    stopLive()
    liveModeActive.value = false
    cameraError.value = t('inbound.camera.unavailable')
  }
}

function stopLive(): void {
  scanControls?.stop()
  scanControls = null
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
}

function shoot(): void {
  const video = videoRef.value
  if (!video || video.videoWidth === 0) return
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  canvas.toBlob(
    (blob) => {
      if (!blob) return
      emit('capture', { blob, filename: `capture-${Date.now()}.jpg` })
    },
    'image/jpeg',
    0.9,
  )
}

function onFileInputChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    emit('capture', { blob: file, filename: file.name })
  }
  input.value = ''
}

/** Triggers one capture, regardless of which mode is active — called by the parent's "拍照" / "＋加拍同件" buttons. */
function capturePhoto(): void {
  if (liveModeActive.value) {
    shoot()
  } else {
    fileInputRef.value?.click()
  }
}

onMounted(() => {
  // Attempt the getUserMedia path automatically; on any failure the
  // file-input fallback (already rendered, see template) takes over — this
  // is the "getUserMedia 不可用時自動降級" behaviour from 06 §2.
  void startLive()
})

onBeforeUnmount(() => {
  stopLive()
})

defineExpose({ capturePhoto, startLive })
</script>

<template>
  <div class="camera-capture">
    <div
      v-if="liveModeActive"
      class="camera-capture__live"
    >
      <div class="camera-capture__video-wrap">
        <video
          ref="videoRef"
          class="camera-capture__video"
          playsinline
          muted
          aria-hidden="true"
        />
        <div
          class="camera-capture__scan-frame"
          aria-hidden="true"
        />
      </div>
      <p
        class="camera-capture__barcode-status"
        aria-live="polite"
      >
        {{
          lastDetectedBarcode
            ? t('inbound.camera.barcodeDetected', { value: lastDetectedBarcode })
            : t('inbound.camera.scanning')
        }}
      </p>
    </div>
    <div
      v-else
      class="camera-capture__fallback"
    >
      <p
        v-if="cameraError"
        class="camera-capture__error"
        role="status"
      >
        {{ cameraError }}
      </p>
      <p
        v-else
        class="camera-capture__hint"
      >
        {{ t('inbound.camera.fileFallbackHint') }}
      </p>
    </div>
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      capture="environment"
      class="camera-capture__file-input"
      :aria-label="t('inbound.camera.openCamera')"
      @change="onFileInputChange"
    >
  </div>
</template>

<style scoped>
.camera-capture {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.camera-capture__video-wrap {
  position: relative;
  width: 100%;
  max-width: 480px;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background-color: #000;
}

.camera-capture__video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-capture__scan-frame {
  position: absolute;
  inset: 15% 10%;
  border: 3px solid var(--oi-blue);
  border-radius: var(--radius-md);
  pointer-events: none;
}

.camera-capture__barcode-status {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.camera-capture__fallback {
  padding: var(--space-4);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.camera-capture__hint,
.camera-capture__error {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.camera-capture__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

/* Native file input stays in the DOM (so `capturePhoto()` can .click() it)
   but is visually hidden — the parent page supplies the visible, >=44px
   trigger buttons ("拍照" / "＋加拍同件"). */
.camera-capture__file-input {
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
</style>

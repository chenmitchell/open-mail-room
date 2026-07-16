<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/AppButton.vue'
import { useUid } from '@/composables/useUid'

// 06 §1 領取核銷頁: touch-capable signature capture, output as PNG base64
// (02 attachments: "簽名以 PNG 存檔,不存筆跡向量"). Pointer Events cover
// mouse + touch + pen in one code path. `touch-action: none` on the canvas
// stops the page from scrolling while the counter is signing on a phone.
//
// Accessibility note: freehand signing is inherently a pointer-only gesture
// (like signing on paper) and has no keyboard equivalent — this mirrors
// physical signature capture devices. The pickup page always offers the
// pickup-code method as a fully keyboard-operable alternative (06 §1).
const props = withDefaults(
  defineProps<{
    width?: number
    height?: number
    disabled?: boolean
  }>(),
  {
    width: 600,
    height: 200,
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  change: [value: string | null]
}>()

const { t } = useI18n({ useScope: 'global' })

const canvasRef = ref<HTMLCanvasElement | null>(null)
const isEmpty = ref(true)
const labelId = useUid('signature-pad-label')

let ctx: CanvasRenderingContext2D | null = null
let drawing = false
let lastPoint: { x: number; y: number } | null = null

function getContext(): CanvasRenderingContext2D | null {
  if (!ctx && canvasRef.value) {
    ctx = canvasRef.value.getContext('2d')
    if (ctx) {
      ctx.lineWidth = 2.5
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.strokeStyle = '#1a1a1a'
    }
  }
  return ctx
}

function pointFromEvent(event: PointerEvent): { x: number; y: number } | null {
  const canvas = canvasRef.value
  if (!canvas) return null
  const rect = canvas.getBoundingClientRect()
  const scaleX = canvas.width / (rect.width || canvas.width)
  const scaleY = canvas.height / (rect.height || canvas.height)
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
  }
}

function onPointerDown(event: PointerEvent) {
  if (props.disabled) return
  const context = getContext()
  if (!context) return
  drawing = true
  lastPoint = pointFromEvent(event)
  canvasRef.value?.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!drawing || props.disabled) return
  const context = getContext()
  const point = pointFromEvent(event)
  if (!context || !point || !lastPoint) return
  context.beginPath()
  context.moveTo(lastPoint.x, lastPoint.y)
  context.lineTo(point.x, point.y)
  context.stroke()
  lastPoint = point
  isEmpty.value = false
}

function stopDrawing() {
  if (!drawing) return
  drawing = false
  lastPoint = null
  emitValue()
}

function emitValue() {
  const value = exportPng()
  emit('update:modelValue', value)
  emit('change', value)
}

/** Returns the signature as base64 PNG (no `data:` prefix), or null if empty. */
function exportPng(): string | null {
  const canvas = canvasRef.value
  if (!canvas || isEmpty.value) return null
  const dataUrl = canvas.toDataURL('image/png')
  const [, base64] = dataUrl.split(',')
  return base64 ?? null
}

function clear() {
  const context = getContext()
  const canvas = canvasRef.value
  if (context && canvas) {
    context.clearRect(0, 0, canvas.width, canvas.height)
  }
  isEmpty.value = true
  emit('update:modelValue', null)
  emit('change', null)
}

onMounted(() => {
  // Ensure a fresh, correctly-styled context as soon as the canvas exists.
  getContext()
})

onBeforeUnmount(() => {
  drawing = false
})

defineExpose({ clear, exportPng, isEmpty })
</script>

<template>
  <div class="signature-pad">
    <p
      :id="labelId"
      class="signature-pad__label"
    >
      {{ t('pickup.signatureLabel') }}
    </p>
    <canvas
      ref="canvasRef"
      class="signature-pad__canvas"
      :class="{ 'signature-pad__canvas--disabled': disabled }"
      :width="width"
      :height="height"
      role="img"
      :aria-labelledby="labelId"
      :aria-describedby="`${labelId}-hint`"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="stopDrawing"
      @pointercancel="stopDrawing"
      @pointerleave="stopDrawing"
    />
    <p
      :id="`${labelId}-hint`"
      class="signature-pad__hint"
    >
      {{ t('pickup.signatureHint') }}
    </p>
    <AppButton
      variant="secondary"
      type="button"
      :disabled="disabled"
      @click="clear"
    >
      {{ t('pickup.signatureClear') }}
    </AppButton>
  </div>
</template>

<style scoped>
.signature-pad {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.signature-pad__label {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.signature-pad__canvas {
  width: 100%;
  max-width: 600px;
  height: auto;
  aspect-ratio: 3 / 1;
  touch-action: none;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  background-color: #ffffff;
  cursor: crosshair;
}

.signature-pad__canvas--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.signature-pad__hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
</style>

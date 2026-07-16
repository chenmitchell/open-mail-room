<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useUid } from '@/composables/useUid'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    closeOnBackdrop?: boolean
    /** 'drawer' slides in from the right (查詢頁詳情面板); 'modal' is centred. */
    variant?: 'modal' | 'drawer'
  }>(),
  {
    closeOnBackdrop: true,
    variant: 'modal',
  },
)

const emit = defineEmits<{ close: [] }>()

const dialogRef = ref<HTMLElement | null>(null)
const titleId = useUid('app-dialog-title')
let lastFocused: HTMLElement | null = null
// POLISH-AUDIT.md Nice #16: without this, the page behind an open dialog
// (modal *or* drawer) keeps scrolling under a fixed-position backdrop --
// confusing on touch devices especially. Saves/restores the previous inline
// value rather than assuming it was always empty, in case some page ever
// sets its own `body.style.overflow`.
let previousBodyOverflow = ''

function getFocusable(): HTMLElement[] {
  if (!dialogRef.value) return []
  return Array.from(
    dialogRef.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  )
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key === 'Tab') {
    const focusable = getFocusable()
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
}

function onBackdropClick() {
  if (props.closeOnBackdrop) emit('close')
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      previousBodyOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      lastFocused = document.activeElement as HTMLElement | null
      await nextTick()
      const focusable = getFocusable()
      ;(focusable[0] ?? dialogRef.value)?.focus()
      document.addEventListener('keydown', onKeydown)
    } else {
      document.body.style.overflow = previousBodyOverflow
      document.removeEventListener('keydown', onKeydown)
      lastFocused?.focus()
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  if (props.open) {
    document.body.style.overflow = previousBodyOverflow
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="app-dialog-backdrop"
      :class="{ 'app-dialog-backdrop--drawer': variant === 'drawer' }"
      @mousedown.self="onBackdropClick"
    >
      <div
        ref="dialogRef"
        class="app-dialog"
        :class="{ 'app-dialog--drawer': variant === 'drawer' }"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="app-dialog__header">
          <h2
            :id="titleId"
            class="app-dialog__title"
          >
            {{ title }}
          </h2>
          <button
            type="button"
            class="app-dialog__close"
            :aria-label="$t('common.close')"
            @click="emit('close')"
          >
            <span aria-hidden="true">&times;</span>
          </button>
        </header>
        <div class="app-dialog__body">
          <slot />
        </div>
        <footer
          v-if="$slots.footer"
          class="app-dialog__footer"
        >
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.app-dialog-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  z-index: 100;
}

.app-dialog {
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
  background-color: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.app-dialog-backdrop--drawer {
  justify-content: flex-end;
  padding: 0;
}

.app-dialog--drawer {
  max-width: 420px;
  height: 100%;
  max-height: 100vh;
  border-radius: 0;
}

@media (prefers-reduced-motion: no-preference) {
  .app-dialog--drawer {
    animation: app-dialog-slide-in 0.2s ease-out;
  }
}

@keyframes app-dialog-slide-in {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

.app-dialog:focus {
  outline: none;
}

.app-dialog__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.app-dialog__title {
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0;
}

.app-dialog__close {
  min-width: var(--touch-target-min);
  min-height: var(--touch-target-min);
  border: none;
  background: transparent;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: var(--color-text);
  border-radius: var(--radius-md);
}

.app-dialog__close:hover {
  background-color: var(--color-bg-subtle);
}

.app-dialog__body {
  color: var(--color-text);
}

.app-dialog__footer {
  margin-top: var(--space-5);
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}
</style>

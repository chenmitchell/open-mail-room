<script setup lang="ts">
import { useUid } from '@/composables/useUid'

// Used for the confidential/COD/refrigeration branding-feature toggles (06
// §1 手動登記頁). role="switch" + aria-checked keeps state programmatically
// exposed; the label text is the primary carrier of meaning (colour is only
// a supporting cue), and the whole control meets the >=44px touch target.
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    label: string
    hint?: string | null
    disabled?: boolean
  }>(),
  {
    hint: null,
    disabled: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const hintId = useUid('app-toggle-hint')

function toggle() {
  if (props.disabled) return
  emit('update:modelValue', !props.modelValue)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    toggle()
  }
}
</script>

<template>
  <div class="app-toggle">
    <button
      type="button"
      role="switch"
      class="app-toggle__control"
      :class="{ 'app-toggle__control--on': modelValue }"
      :aria-checked="modelValue"
      :aria-describedby="hint ? hintId : undefined"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span
        class="app-toggle__track"
        aria-hidden="true"
      >
        <span class="app-toggle__thumb" />
      </span>
      <span class="app-toggle__label">{{ label }}</span>
      <span
        class="app-toggle__state"
        aria-hidden="true"
      >{{
        modelValue ? $t('common.on') : $t('common.off')
      }}</span>
    </button>
    <p
      v-if="hint"
      :id="hintId"
      class="app-toggle__hint"
    >
      {{ hint }}
    </p>
  </div>
</template>

<style scoped>
.app-toggle {
  margin-bottom: var(--space-3);
}

.app-toggle__control {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg);
  cursor: pointer;
  width: 100%;
  text-align: left;
}

.app-toggle__control:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.app-toggle__track {
  flex-shrink: 0;
  width: 40px;
  height: 24px;
  border-radius: var(--radius-full);
  background-color: var(--color-border);
  position: relative;
  transition: background-color 0.15s ease;
}

.app-toggle__control--on .app-toggle__track {
  background-color: var(--brand-primary);
}

.app-toggle__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: #ffffff;
  transition: transform 0.15s ease;
}

.app-toggle__control--on .app-toggle__thumb {
  transform: translateX(16px);
}

.app-toggle__label {
  flex: 1;
  font-weight: 600;
  color: var(--color-text);
}

.app-toggle__state {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-weight: 600;
}

.app-toggle__hint {
  margin: var(--space-1) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

@media (prefers-reduced-motion: reduce) {
  .app-toggle__track,
  .app-toggle__thumb {
    transition: none;
  }
}
</style>

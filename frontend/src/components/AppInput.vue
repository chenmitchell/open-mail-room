<script setup lang="ts">
import { computed } from 'vue'
import { useUid } from '@/composables/useUid'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    type?: string
    placeholder?: string
    error?: string | null
    hint?: string | null
    required?: boolean
    disabled?: boolean
    autocomplete?: string
  }>(),
  {
    type: 'text',
    placeholder: '',
    error: null,
    hint: null,
    required: false,
    disabled: false,
    autocomplete: undefined,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const inputId = useUid('app-input')
const errorId = computed(() => `${inputId}-error`)
const hintId = computed(() => `${inputId}-hint`)

const describedBy = computed(() => {
  const ids = [props.hint ? hintId.value : null, props.error ? errorId.value : null].filter(
    Boolean,
  )
  return ids.length ? ids.join(' ') : undefined
})

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="app-input">
    <label
      :for="inputId"
      class="app-input__label"
    >
      {{ label }}
      <span
        v-if="required"
        class="app-input__required"
      >({{ $t('common.required') }})</span>
      <span
        v-else
        class="app-input__optional"
      >({{ $t('common.optional') }})</span>
    </label>
    <input
      :id="inputId"
      class="app-input__field"
      :class="{ 'app-input__field--error': !!error }"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :autocomplete="autocomplete"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @input="onInput"
    >
    <p
      v-if="hint"
      :id="hintId"
      class="app-input__hint"
    >
      {{ hint }}
    </p>
    <p
      v-if="error"
      :id="errorId"
      class="app-input__error"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.app-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}

.app-input__label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.app-input__required {
  /* Muted grey rather than a loud status colour (oi-vermillion is reserved
   * for actual validation errors) — "required" should read as informative,
   * not alarming, while still holding >= 7:1 contrast on white
   * (--color-text-muted #4a4a4a ~= 8.9:1). */
  color: var(--color-text-muted);
  font-weight: 600;
}

.app-input__optional {
  color: var(--color-text-muted);
  font-weight: 400;
}

.app-input__field {
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-base);
  font-family: var(--font-family-base);
  color: var(--color-text);
  background-color: var(--color-bg);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
}

.app-input__field:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-ring-offset);
  border-color: var(--brand-primary);
}

.app-input__field--error {
  border-color: var(--oi-vermillion);
}

.app-input__hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
}

.app-input__error {
  font-size: var(--font-size-sm);
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0;
}
</style>

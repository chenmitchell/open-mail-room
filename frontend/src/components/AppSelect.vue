<script setup lang="ts">
import { computed } from 'vue'
import { useUid } from '@/composables/useUid'

export interface AppSelectOption {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    options: AppSelectOption[]
    placeholder?: string
    /** POLISH-AUDIT.md Should-fix #6: when the empty-value option is a
     * legitimate selectable choice (e.g. a "any status / all" filter on
     * SearchPage/OutboundPage/EmployeesAdminPage that the user should be
     * able to select back to), the placeholder <option> must NOT be
     * `disabled` -- disabled makes it unreachable once another option has
     * been picked (a native <select> can't re-select a disabled option).
     * Defaults to false to keep required-field selects (where the empty
     * value is only a prompt, never a valid submission) behaving as before. */
    placeholderSelectable?: boolean
    error?: string | null
    hint?: string | null
    required?: boolean
    disabled?: boolean
  }>(),
  {
    placeholder: undefined,
    placeholderSelectable: false,
    error: null,
    hint: null,
    required: false,
    disabled: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const selectId = useUid('app-select')
const errorId = computed(() => `${selectId}-error`)
const hintId = computed(() => `${selectId}-hint`)

const describedBy = computed(() => {
  const ids = [props.hint ? hintId.value : null, props.error ? errorId.value : null].filter(
    Boolean,
  )
  return ids.length ? ids.join(' ') : undefined
})

function onChange(event: Event) {
  emit('update:modelValue', (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="app-select">
    <label
      :for="selectId"
      class="app-select__label"
    >
      {{ label }}
      <span
        v-if="required"
        class="app-select__required"
      >({{ $t('common.required') }})</span>
      <span
        v-else
        class="app-select__optional"
      >({{ $t('common.optional') }})</span>
    </label>
    <select
      :id="selectId"
      class="app-select__field"
      :class="{ 'app-select__field--error': !!error }"
      :value="modelValue"
      :disabled="disabled"
      :required="required"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      @change="onChange"
    >
      <option
        v-if="placeholder"
        value=""
        :disabled="!placeholderSelectable"
      >
        {{ placeholder }}
      </option>
      <option
        v-for="opt in options"
        :key="opt.value"
        :value="opt.value"
      >
        {{ opt.label }}
      </option>
    </select>
    <p
      v-if="hint"
      :id="hintId"
      class="app-select__hint"
    >
      {{ hint }}
    </p>
    <p
      v-if="error"
      :id="errorId"
      class="app-select__error"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.app-select {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}

.app-select__label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.app-select__required {
  /* Muted grey rather than a loud status colour (oi-vermillion is reserved
   * for actual validation errors) — "required" should read as informative,
   * not alarming, while still holding >= 7:1 contrast on white
   * (--color-text-muted #4a4a4a ~= 8.9:1). */
  color: var(--color-text-muted);
  font-weight: 600;
}

.app-select__optional {
  color: var(--color-text-muted);
  font-weight: 400;
}

.app-select__field {
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-base);
  font-family: var(--font-family-base);
  color: var(--color-text);
  background-color: var(--color-bg);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
}

.app-select__field:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-ring-offset);
  border-color: var(--brand-primary);
}

.app-select__field--error {
  border-color: var(--oi-vermillion);
}

.app-select__hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
}

.app-select__error {
  font-size: var(--font-size-sm);
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0;
}
</style>

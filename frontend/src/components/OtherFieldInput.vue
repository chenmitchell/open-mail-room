<script setup lang="ts">
// UX-VISUAL task B: shared "選其他 -> 即時展開必填輸入框" widget. Wraps
// AppInput so it inherits the same label/required/error/focus-ring
// treatment as every other field, but only renders (and is only wired up as
// `required`) while the paired dropdown's `show` condition is true — see
// src/composables/useOtherOption.ts for how callers derive `show`.
import AppInput from './AppInput.vue'

defineProps<{
  show: boolean
  modelValue: string
  label: string
  error?: string | null
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <AppInput
    v-if="show"
    class="other-field-input"
    :model-value="modelValue"
    :label="label"
    :error="error"
    required
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<style scoped>
.other-field-input {
  /* Slight left indent + accent rail so the just-revealed field visually
   * reads as "belonging to" the dropdown above it, not just another
   * unrelated form row. */
  padding-left: var(--space-3);
  border-left: 3px solid var(--brand-primary);
}
</style>

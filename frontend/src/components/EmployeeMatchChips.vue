<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { EmployeeMatchCandidate } from '@/types/api'

// 01 §5 模糊比對候選: 分數 >=90 自動帶入、70-90 列候選、<70 留空.
// 06 §1 OCR 確認頁/手動登記頁: 「員工比對候選 chips(分數與部門)」。
// Selection is keyboard + screen-reader operable (native <button>,
// aria-pressed) and colour is never the only signal — the score number and
// "high confidence" wording are always shown as text alongside the tone.
const props = defineProps<{
  candidates: EmployeeMatchCandidate[]
  modelValue: string | null
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

const { t } = useI18n({ useScope: 'global' })

function confidenceLabel(score: number): string {
  if (score >= 90) return t('inbound.matchHighConfidence')
  if (score >= 70) return t('inbound.matchMediumConfidence')
  return t('inbound.matchLowConfidence')
}

function select(candidate: EmployeeMatchCandidate) {
  const next = props.modelValue === candidate.employee_id ? null : candidate.employee_id
  emit('update:modelValue', next)
}
</script>

<template>
  <ul
    v-if="candidates.length"
    class="employee-match-chips"
    :aria-label="t('inbound.matchCandidates')"
  >
    <li
      v-for="candidate in candidates"
      :key="candidate.employee_id"
    >
      <button
        type="button"
        class="employee-match-chips__chip"
        :class="{
          'employee-match-chips__chip--selected': modelValue === candidate.employee_id,
          'employee-match-chips__chip--high': candidate.score >= 90,
        }"
        :aria-pressed="modelValue === candidate.employee_id"
        @click="select(candidate)"
      >
        <span class="employee-match-chips__name">{{ candidate.name }}</span>
        <span
          v-if="candidate.department_name"
          class="employee-match-chips__dept"
        >{{
          candidate.department_name
        }}</span>
        <span class="employee-match-chips__score">{{ confidenceLabel(candidate.score) }} · {{ Math.round(candidate.score) }}%</span>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.employee-match-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
  padding: 0;
}

.employee-match-chips__chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  border: 2px solid var(--color-border);
  background-color: var(--color-bg);
  color: var(--color-text);
  cursor: pointer;
  text-align: left;
}

.employee-match-chips__chip--high {
  border-color: var(--oi-blue);
}

.employee-match-chips__chip--selected {
  background-color: var(--brand-primary);
  border-color: var(--brand-primary);
  color: var(--brand-primary-contrast);
}

.employee-match-chips__name {
  font-weight: 700;
}

.employee-match-chips__dept,
.employee-match-chips__score {
  font-size: var(--font-size-xs);
}
</style>

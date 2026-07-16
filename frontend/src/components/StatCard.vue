<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: number | string
    loading?: boolean
    // M8-3 designer layout: 滯留 (stranded/unclaimed) reads in the AAA-safe
    // deep-red text token so it stands out from the neutral stat cards,
    // without colour being the only signal -- the label + icon-free bold
    // number is still readable/nameable on its own (06 §3).
    tone?: 'default' | 'warning'
  }>(),
  {
    loading: false,
    tone: 'default',
  },
)
</script>

<template>
  <div class="stat-card">
    <p class="stat-card__label">
      {{ label }}
    </p>
    <p
      class="stat-card__value"
      :class="{ 'stat-card__value--warning': tone === 'warning' }"
      aria-live="polite"
    >
      <span
        v-if="loading"
        class="stat-card__loading"
      >{{ $t('common.loading') }}</span>
      <span v-else>{{ value }}</span>
    </p>
  </div>
</template>

<style scoped>
.stat-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.stat-card__label {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-weight: 600;
}

.stat-card__value {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text);
}

.stat-card__value--warning {
  color: var(--color-danger-text);
}

.stat-card__loading {
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
  font-weight: 400;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
type ButtonType = 'button' | 'submit' | 'reset'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    type?: ButtonType
    disabled?: boolean
    loading?: boolean
    fullWidth?: boolean
  }>(),
  {
    variant: 'primary',
    type: 'button',
    disabled: false,
    loading: false,
    fullWidth: false,
  },
)

const isDisabled = computed(() => props.disabled || props.loading)
</script>

<template>
  <button
    :type="type"
    class="app-button"
    :class="[
      `app-button--${variant}`,
      { 'app-button--full': fullWidth, 'app-button--loading': loading },
    ]"
    :disabled="isDisabled"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span
      v-if="loading"
      class="app-button__spinner"
      aria-hidden="true"
    />
    <span class="app-button__label"><slot /></span>
  </button>
</template>

<style scoped>
.app-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: var(--touch-target-min);
  min-width: var(--touch-target-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  border: 2px solid transparent;
  font-family: var(--font-family-base);
  font-size: var(--font-size-base);
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    opacity 0.15s ease;
}

.app-button--full {
  width: 100%;
}

.app-button--primary {
  background-color: var(--brand-primary);
  color: var(--brand-primary-contrast);
  border-color: var(--brand-primary);
}
.app-button--primary:hover:not(:disabled) {
  filter: brightness(0.9);
}

.app-button--secondary {
  background-color: transparent;
  color: var(--brand-primary);
  border-color: var(--brand-primary);
}
.app-button--secondary:hover:not(:disabled) {
  background-color: var(--color-bg-subtle);
}

.app-button--danger {
  /* POLISH-AUDIT.md Blocking #13: --oi-vermillion (#d55e00) only reaches
   * ~3.87:1 with white label text (AA-large at best) -- --color-danger-strong
   * is a deeper, fixed (non-dark-mode-adaptive) red tuned for >=7:1 white-text
   * contrast in every colour scheme (see tokens.css). */
  background-color: var(--color-danger-strong);
  color: #ffffff;
  border-color: var(--color-danger-strong);
}
.app-button--danger:hover:not(:disabled) {
  filter: brightness(0.9);
}

.app-button--ghost {
  background-color: transparent;
  color: var(--color-text);
  border-color: var(--color-border);
}
.app-button--ghost:hover:not(:disabled) {
  background-color: var(--color-bg-subtle);
}

/* Disabled state: an explicit "muted grey" look (background/text/border all
 * swap to the neutral disabled tokens), not a washed-out translucent version
 * of the brand colour — a semi-transparent primary button reads as "still
 * clickable, just loading" rather than "unavailable". Token specificity
 * (.app-button:disabled = 2 selectors) already beats the single-class
 * .app-button--<variant> rules above, so this overrides every variant. */
.app-button:disabled {
  cursor: not-allowed;
  background-color: var(--color-bg-subtle);
  color: var(--color-text-muted);
  border-color: var(--color-border);
}

.app-button__spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-top-color: transparent;
  animation: app-button-spin 0.7s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .app-button__spinner {
    animation: none;
    opacity: 0.6;
  }
}

@keyframes app-button-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

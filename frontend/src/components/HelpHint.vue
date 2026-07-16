<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUid } from '@/composables/useUid'

// M6-HELP: small reusable "?" hint icon placed next to a page/section title.
// Hover *or* keyboard focus reveals a self-drawn tooltip explaining what the
// screen is for (task brief: "用 title 屬性 + 自繪 tooltip,鍵盤可聚焦、
// aria-describedby"). The native `title` attribute is kept as a browser-level
// fallback tooltip; the accessible *name* stays a generic "help" label
// (`help.hintAriaLabel`) so every hint reads consistently to a screen
// reader, while the specific explanation is exposed as the accessible
// *description* via aria-describedby -- that's why the tooltip text isn't
// also stuffed into aria-label (would double-announce the same string).
//
// The tooltip node stays permanently mounted (never v-if'd) and only ever
// toggles `opacity`/`pointer-events` -- display:none/visibility:hidden would
// pull it out of the accessibility tree and break aria-describedby for
// screen-reader users even though the visual hover/focus reveal is exactly
// what sighted mouse/keyboard users see.
const props = defineProps<{
  text: string
}>()

const { t } = useI18n({ useScope: 'global' })

const tooltipId = useUid('help-hint')
const visible = ref(false)

function show() {
  visible.value = true
}
function hide() {
  visible.value = false
}
</script>

<template>
  <span class="help-hint">
    <button
      type="button"
      class="help-hint__trigger"
      :title="props.text"
      :aria-label="t('help.hintAriaLabel')"
      :aria-describedby="tooltipId"
      @mouseenter="show"
      @mouseleave="hide"
      @focus="show"
      @blur="hide"
    >
      <svg
        class="help-hint__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r="9"
        />
        <path d="M9.2 9a2.8 2.8 0 115.2 1.5c-.7.9-1.9 1.3-1.9 2.7" />
        <path d="M12 17.2h.01" />
      </svg>
    </button>
    <span
      :id="tooltipId"
      role="tooltip"
      class="help-hint__tooltip"
      :class="{ 'help-hint__tooltip--visible': visible }"
    >
      {{ props.text }}
    </span>
  </span>
</template>

<style scoped>
.help-hint {
  position: relative;
  display: inline-flex;
}

.help-hint__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--touch-target-min);
  min-height: var(--touch-target-min);
  padding: 0;
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}

.help-hint__trigger:hover {
  color: var(--brand-primary);
  background-color: var(--color-bg-subtle);
}

.help-hint__icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.help-hint__tooltip {
  position: absolute;
  z-index: 20;
  top: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  width: max-content;
  max-width: 260px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background-color: var(--color-text);
  color: var(--color-text-inverse);
  font-size: var(--font-size-sm);
  font-weight: 500;
  line-height: var(--line-height-tight);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.help-hint__tooltip--visible {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .help-hint__tooltip {
    transition: none;
  }
}
</style>

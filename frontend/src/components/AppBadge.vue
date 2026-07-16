<script setup lang="ts">
import { computed } from 'vue'

// M8-2 密集晶片版 (designer "badges" spec): every status renders as a
// coloured chip (status bg + status fg icon) + a bold black text label,
// never colour alone — chip colour / icon shape / text are three
// independent channels, matching 06-UI-UX.md §3 "顏色永不作為唯一訊息載體".
// The outer pill itself stays neutral (white bg, --color-border-subtle
// hairline) so the status colour lives only in the chip, per the designer
// badges spec.
export type BadgeStatus =
  | 'pending'
  | 'notified'
  | 'pickedUp'
  | 'reminder'
  | 'unclaimed'
  | 'outbound'
  | 'neutral'

const props = withDefaults(
  defineProps<{
    status: BadgeStatus
    label?: string
  }>(),
  {
    label: undefined,
  },
)

// Icon shapes are deliberately distinct per status (redundant with chip
// colour + text, never relied on alone): pending=clock, notified=bell,
// pickedUp=check, reminder=warning triangle, unclaimed=alert circle
// (visually distinct silhouette from reminder's triangle), outbound=arrow,
// neutral=plus (roles / generic).
const ICON_PATHS: Record<BadgeStatus, string[]> = {
  pending: ['M12 21a9 9 0 100-18 9 9 0 000 18z', 'M12 7v5l3 3'],
  notified: ['M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9', 'M13.73 21a2 2 0 01-3.46 0'],
  pickedUp: ['M20 6L9 17l-5-5'],
  reminder: [
    'M12 9v4',
    'M12 17h.01',
    'M10.29 3.86L1.82 18a1 1 0 00.87 1.5h18.62a1 1 0 00.87-1.5L13.71 3.86a1 1 0 00-1.72 0z',
  ],
  unclaimed: ['M12 8v5', 'M12 16.5h.01', 'M12 22a10 10 0 100-20 10 10 0 000 20z'],
  outbound: ['M5 12h14', 'M13 6l6 6-6 6'],
  neutral: ['M12 8v8', 'M8 12h8'],
}

const iconPaths = computed(() => ICON_PATHS[props.status])
const label = computed(() => props.label ?? props.status)
</script>

<template>
  <span
    class="app-badge"
    :class="`app-badge--${status}`"
  >
    <span
      class="app-badge__chip"
      aria-hidden="true"
    >
      <svg
        class="app-badge__icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path
          v-for="(d, idx) in iconPaths"
          :key="idx"
          :d="d"
        />
      </svg>
    </span>
    <span class="app-badge__label"><slot>{{ label }}</slot></span>
  </span>
</template>

<style scoped>
/* Dense chip pill: 28px tall, white pill + subtle hairline border, a
   colour-filled rounded-square chip on the left (icon in the status's fg
   colour) and a bold black label on the right. --app-badge-min-width lets
   a list container force same-width badges (06 spec "等寬對齊"); default
   `auto` keeps standalone badges (nav, dashboard panel titles) dense/compact. */
.app-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 28px;
  box-sizing: border-box;
  padding: 2px var(--space-3) 2px 2px;
  min-width: var(--app-badge-min-width, auto);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-subtle);
  background-color: var(--color-bg-elevated);
  color: var(--color-text);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.app-badge__chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
}

.app-badge__icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.app-badge__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-badge--pending .app-badge__chip {
  background-color: var(--status-pending-bg);
  color: var(--status-pending-fg);
}

.app-badge--notified .app-badge__chip {
  background-color: var(--status-notified-bg);
  color: var(--status-notified-fg);
}

.app-badge--pickedUp .app-badge__chip {
  background-color: var(--status-picked-up-bg);
  color: var(--status-picked-up-fg);
}

.app-badge--reminder .app-badge__chip {
  background-color: var(--status-reminder-bg);
  color: var(--status-reminder-fg);
}

.app-badge--unclaimed .app-badge__chip {
  background-color: var(--status-unclaimed-bg);
  color: var(--status-unclaimed-fg);
}

.app-badge--outbound .app-badge__chip {
  background-color: var(--status-outbound-bg);
  color: var(--status-outbound-fg);
}

/* Neutral (roles / generic, no specific status semantics): a grey chip,
   dark icon — still chip + icon + text, just without an Okabe-Ito hue. */
.app-badge--neutral .app-badge__chip {
  background-color: var(--color-border-subtle);
  color: var(--color-text);
}
</style>

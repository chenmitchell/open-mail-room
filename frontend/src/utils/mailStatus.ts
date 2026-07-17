import type { BadgeStatus } from '@/components/AppBadge.vue'
import type { MailItemStatus } from '@/types/api'

/**
 * Maps the inbound state machine (01-REQUIREMENTS.md §3:
 * received -> notified -> picked_up, branches returned/forwarded/unclaimed/
 * destroyed) onto AppBadge's fixed Okabe-Ito variants, per the task brief:
 * received=oi-orange, notified=oi-skyblue, picked_up=oi-green,
 * unclaimed=oi-vermillion. AppBadge's `pending` variant already carries
 * oi-orange, so `received` reuses it — the badge component itself is the
 * single source of truth for the colour tokens (never remap them here).
 */
const STATUS_TO_BADGE: Record<MailItemStatus, BadgeStatus> = {
  received: 'pending',
  notified: 'notified',
  picked_up: 'pickedUp',
  unclaimed: 'unclaimed',
  returned: 'neutral',
  forwarded: 'neutral',
  destroyed: 'neutral',
  voided: 'neutral',
}

const STATUS_TO_LABEL_KEY: Record<MailItemStatus, string> = {
  received: 'status.received',
  notified: 'status.notified',
  picked_up: 'status.pickedUp',
  unclaimed: 'status.unclaimed',
  returned: 'status.returned',
  forwarded: 'status.forwarded',
  destroyed: 'status.destroyed',
  voided: 'status.voided',
}

export function mailStatusBadgeVariant(status: MailItemStatus): BadgeStatus {
  return STATUS_TO_BADGE[status]
}

export function mailStatusLabelKey(status: MailItemStatus): string {
  return STATUS_TO_LABEL_KEY[status]
}

import type { BadgeStatus } from '@/components/AppBadge.vue'
import type { OutboundStatus } from '@/types/api'

/**
 * Maps the outbound state machine (01-REQUIREMENTS.md §3 「交寄欄位」:
 * 狀態(待交寄/已交寄/已送達/異常), backend/app/models/enums.py
 * `OutboundStatus`) onto AppBadge's fixed Okabe-Ito variants.
 * `shipped` -> the `outbound` variant is a direct match: 06-UI-UX.md §3's
 * token table assigns oi-purple's meaning as literally "交寄". `delivered`
 * reuses the green "success" variant and `exception` reuses the vermillion
 * "error" variant — same reasoning as src/utils/mailStatus.ts, never remap
 * the token colours themselves, only which fixed variant a status maps to.
 */
const STATUS_TO_BADGE: Record<OutboundStatus, BadgeStatus> = {
  pending: 'pending',
  shipped: 'outbound',
  delivered: 'pickedUp',
  exception: 'unclaimed',
}

const STATUS_TO_LABEL_KEY: Record<OutboundStatus, string> = {
  pending: 'outbound.status.pending',
  shipped: 'outbound.status.shipped',
  delivered: 'outbound.status.delivered',
  exception: 'outbound.status.exception',
}

export function outboundStatusBadgeVariant(status: OutboundStatus): BadgeStatus {
  return STATUS_TO_BADGE[status]
}

export function outboundStatusLabelKey(status: OutboundStatus): string {
  return STATUS_TO_LABEL_KEY[status]
}

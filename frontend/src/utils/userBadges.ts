import type { BadgeStatus } from '@/components/AppBadge.vue'
import type { Role } from '@/types/api'

// M7-FE UsersAdminPage: maps roles/account-status onto AppBadge's fixed
// Okabe-Ito variants, same convention as src/utils/mailStatus.ts (reuse the
// existing palette rather than adding new colours to the shared component).
const ROLE_TO_BADGE: Record<Role, BadgeStatus> = {
  admin: 'outbound', // purple — the most privileged role, visually distinct
  counter: 'notified', // sky blue
  employee: 'pickedUp', // green
  viewer: 'neutral', // grey
}

export function roleBadgeVariant(role: Role): BadgeStatus {
  return ROLE_TO_BADGE[role]
}

// Same green/red convention NotificationSettingsPage.vue already uses for
// verified/unverified bindings.
export function userActiveBadgeVariant(isActive: boolean): BadgeStatus {
  return isActive ? 'pickedUp' : 'unclaimed'
}

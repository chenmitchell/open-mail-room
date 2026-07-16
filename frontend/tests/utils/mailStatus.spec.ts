import { describe, expect, it } from 'vitest'
import { mailStatusBadgeVariant, mailStatusLabelKey } from '@/utils/mailStatus'
import type { MailItemStatus } from '@/types/api'

describe('mailStatus', () => {
  // Task brief: "狀態 badge 用 Okabe-Ito token: received=oi-orange,
  // notified=oi-skyblue, picked_up=oi-green, unclaimed=oi-vermillion" — those
  // colours live on AppBadge's fixed variants (pending/notified/pickedUp/
  // unclaimed), so this asserts the domain status maps onto the correct
  // AppBadge variant (and therefore the correct colour token).
  it.each([
    ['received', 'pending'],
    ['notified', 'notified'],
    ['picked_up', 'pickedUp'],
    ['unclaimed', 'unclaimed'],
    ['returned', 'neutral'],
    ['forwarded', 'neutral'],
    ['destroyed', 'neutral'],
  ] satisfies [MailItemStatus, string][])('%s -> AppBadge variant %s', (status, variant) => {
    expect(mailStatusBadgeVariant(status)).toBe(variant)
  })

  it('every status has a distinct i18n label key', () => {
    const statuses: MailItemStatus[] = [
      'received',
      'notified',
      'picked_up',
      'returned',
      'forwarded',
      'unclaimed',
      'destroyed',
    ]
    const keys = statuses.map(mailStatusLabelKey)
    expect(new Set(keys).size).toBe(statuses.length)
    expect(keys).toContain('status.received')
    expect(keys).toContain('status.unclaimed')
  })
})

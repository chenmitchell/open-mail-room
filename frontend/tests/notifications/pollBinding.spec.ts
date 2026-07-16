import { describe, expect, it, vi } from 'vitest'
import { pollBindingVerified } from '@/notifications/pollBinding'
import type { NotificationBinding } from '@/types/api'

// 05-NOTIFICATIONS.md §3 LINE/Telegram 綁定精靈狀態機: start -> 輪詢 ->
// 成功/逾時(/取消). Uses an injected fake clock/sleep so timing is
// deterministic and instant — same approach as tests/ocr/pollJob.spec.ts.
function fakeClock() {
  let elapsed = 0
  return {
    now: () => elapsed,
    sleep: async (ms: number) => {
      elapsed += ms
    },
  }
}

function makeBinding(overrides: Partial<NotificationBinding> = {}): NotificationBinding {
  return {
    id: 'b1',
    channel: 'line',
    address: 'masked',
    is_verified: false,
    ...overrides,
  }
}

describe('pollBindingVerified', () => {
  it('resolves immediately when a newly-verified binding is already present on the first fetch', async () => {
    const binding = makeBinding({ id: 'b1', channel: 'line', is_verified: true })
    const fetchBindings = vi.fn().mockResolvedValue([binding])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, { now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'verified', binding })
    expect(fetchBindings).toHaveBeenCalledTimes(1)
  })

  it('polls at the configured interval until the binding becomes verified', async () => {
    const responses: NotificationBinding[][] = [
      [],
      [makeBinding({ id: 'b1', channel: 'line', is_verified: false })],
      [makeBinding({ id: 'b1', channel: 'line', is_verified: true })],
    ]
    const fetchBindings = vi.fn().mockImplementation(async () => responses.shift() ?? [])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, {
      intervalMs: 3000,
      timeoutMs: 600000,
      now: clock.now,
      sleep: clock.sleep,
    })

    expect(result.status).toBe('verified')
    expect(fetchBindings).toHaveBeenCalledTimes(3)
  })

  it('ignores a binding that was already verified before the wizard started (knownVerifiedIds)', async () => {
    const preExisting = makeBinding({ id: 'old', channel: 'line', is_verified: true })
    const justVerified = makeBinding({ id: 'new', channel: 'line', is_verified: true })
    const responses: NotificationBinding[][] = [[preExisting], [preExisting, justVerified]]
    const fetchBindings = vi.fn().mockImplementation(async () => responses.shift() ?? [])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, {
      knownVerifiedIds: new Set(['old']),
      intervalMs: 1000,
      timeoutMs: 60000,
      now: clock.now,
      sleep: clock.sleep,
    })

    expect(result).toEqual({ status: 'verified', binding: justVerified })
    expect(fetchBindings).toHaveBeenCalledTimes(2)
  })

  it('ignores a verified binding on a different channel', async () => {
    const responses: NotificationBinding[][] = [
      [makeBinding({ id: 'b1', channel: 'telegram', is_verified: true })],
    ]
    const fetchBindings = vi.fn().mockImplementation(async () => responses.shift() ?? [])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, {
      intervalMs: 1000,
      timeoutMs: 1000,
      now: clock.now,
      sleep: clock.sleep,
    })

    expect(result).toEqual({ status: 'timeout' })
  })

  it('gives up with a timeout result after the 10-minute cap at the 3s default interval (200 polls)', async () => {
    const fetchBindings = vi.fn().mockResolvedValue([])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, { now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'timeout' })
    expect(fetchBindings).toHaveBeenCalledTimes(200)
  })

  it('stops immediately when cancelled before the first fetch', async () => {
    const fetchBindings = vi.fn().mockResolvedValue([])
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, {
      isCancelled: () => true,
      now: clock.now,
      sleep: clock.sleep,
    })

    expect(result).toEqual({ status: 'cancelled' })
    expect(fetchBindings).not.toHaveBeenCalled()
  })

  it('stops on the next check after cancel is requested mid-poll', async () => {
    let cancelled = false
    const responses: NotificationBinding[][] = [[], []]
    const fetchBindings = vi.fn().mockImplementation(async () => {
      const next = responses.shift() ?? []
      cancelled = true // cancel fires right after the first fetch resolves
      return next
    })
    const clock = fakeClock()

    const result = await pollBindingVerified('line', fetchBindings, {
      intervalMs: 1000,
      timeoutMs: 60000,
      now: clock.now,
      sleep: clock.sleep,
      isCancelled: () => cancelled,
    })

    expect(result).toEqual({ status: 'cancelled' })
    expect(fetchBindings).toHaveBeenCalledTimes(1)
  })
})

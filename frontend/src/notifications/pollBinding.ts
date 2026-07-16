// Pure LINE/Telegram binding-code polling state machine (05-NOTIFICATIONS.md
// §3 步驟 1-3: 產生 6 位綁定碼(10 分鐘有效)-> 員工在 LINE/Telegram 對官方
// 帳號/bot 傳送綁定碼 -> 系統的 webhook 收到後核對綁定碼、存 userId 至
// notification_bindings、回覆「綁定成功」).
//
// ASSUMPTION: there is no dedicated "check binding status" endpoint in
// 03-API-SPEC.md §2 — only `POST /me/bindings/line/start` and the plain
// `GET/POST/DELETE /me/bindings` CRUD. So completion is detected by
// re-fetching `GET /me/bindings` and looking for a binding on the target
// channel, verified, that wasn't already present (and therefore already
// verified) when the wizard started — `knownVerifiedIds` guards against a
// stale pre-existing verified binding on the same channel being mistaken for
// "just completed". Revisit if/when M3-01 adds a purpose-built endpoint.
//
// Kept free of Vue/timers-as-globals so it's directly unit-testable with an
// injected clock/sleep, same shape as src/ocr/pollJob.ts.
import type { NotificationBinding, NotificationChannel } from '@/types/api'

export interface PollBindingOptions {
  intervalMs?: number
  timeoutMs?: number
  /** Injectable for tests; defaults to a real setTimeout-based delay. */
  sleep?: (ms: number) => Promise<void>
  /** Injectable clock for tests; defaults to Date.now. */
  now?: () => number
  /** Binding ids on this channel that were already verified before the wizard started. */
  knownVerifiedIds?: Set<string>
  /** Checked before every fetch/sleep so a "取消綁定" button can stop the loop early. */
  isCancelled?: () => boolean
}

export type PollBindingResult =
  | { status: 'verified'; binding: NotificationBinding }
  | { status: 'timeout' }
  | { status: 'cancelled' }

const DEFAULT_INTERVAL_MS = 3000
// 05 §3 point 1: the binding code is valid for 10 minutes, so polling gives
// up on the same schedule the code itself expires.
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function findNewlyVerified(
  bindings: NotificationBinding[],
  channel: NotificationChannel,
  knownVerifiedIds: Set<string>,
): NotificationBinding | undefined {
  return bindings.find(
    (b) => b.channel === channel && b.is_verified && !knownVerifiedIds.has(b.id),
  )
}

/**
 * Polls `fetchBindings` until a newly-verified binding for `channel`
 * appears, or `timeoutMs` elapses. Fetches immediately on entry (so a
 * binding that completed before the wizard even started its first poll
 * resolves without waiting a full interval).
 */
export async function pollBindingVerified(
  channel: NotificationChannel,
  fetchBindings: () => Promise<NotificationBinding[]>,
  options: PollBindingOptions = {},
): Promise<PollBindingResult> {
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const sleep = options.sleep ?? defaultSleep
  const now = options.now ?? Date.now
  const knownVerifiedIds = options.knownVerifiedIds ?? new Set<string>()
  const isCancelled = options.isCancelled ?? (() => false)

  const startedAt = now()

  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (isCancelled()) return { status: 'cancelled' }

    const bindings = await fetchBindings()
    const match = findNewlyVerified(bindings, channel, knownVerifiedIds)
    if (match) return { status: 'verified', binding: match }

    if (isCancelled()) return { status: 'cancelled' }
    if (now() - startedAt >= timeoutMs) return { status: 'timeout' }

    await sleep(intervalMs)

    if (isCancelled()) return { status: 'cancelled' }
    if (now() - startedAt >= timeoutMs) return { status: 'timeout' }
  }
}

// Pure OCR job polling state machine (03-API-SPEC.md §2 "GET /ocr/jobs/{id}
// 輪詢", task brief: "輪詢 GET /ocr/jobs/{id}(2s 間隔,上限 60s)"). Kept free
// of Vue/timers-as-globals so it's directly unit-testable with an injected
// clock/sleep — the confirm page's composable (useOcrPolling) just drives
// this and mirrors the result into refs.
import type { OcrJob } from '@/types/api'

export interface PollOcrJobOptions {
  intervalMs?: number
  timeoutMs?: number
  /** Injectable for tests; defaults to a real setTimeout-based delay. */
  sleep?: (ms: number) => Promise<void>
  /** Injectable clock for tests; defaults to Date.now. */
  now?: () => number
}

export type PollOcrJobResult =
  | { status: 'succeeded'; job: OcrJob }
  | { status: 'failed'; job: OcrJob }
  | { status: 'timeout' }

const DEFAULT_INTERVAL_MS = 2000
const DEFAULT_TIMEOUT_MS = 90000

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Polls `fetchJob` until the job succeeds, fails, or `timeoutMs` elapses.
 * Fetches immediately on entry (so a job that's already done resolves
 * without waiting a full interval), then waits `intervalMs` between
 * subsequent attempts.
 */
export async function pollOcrJob(
  fetchJob: () => Promise<OcrJob>,
  options: PollOcrJobOptions = {},
): Promise<PollOcrJobResult> {
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const sleep = options.sleep ?? defaultSleep
  const now = options.now ?? Date.now

  const startedAt = now()

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await fetchJob()
    if (job.status === 'succeeded') return { status: 'succeeded', job }
    if (job.status === 'failed') return { status: 'failed', job }

    if (now() - startedAt >= timeoutMs) return { status: 'timeout' }

    await sleep(intervalMs)

    if (now() - startedAt >= timeoutMs) return { status: 'timeout' }
  }
}

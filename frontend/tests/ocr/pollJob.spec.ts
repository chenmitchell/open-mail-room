import { describe, expect, it, vi } from 'vitest'
import { pollOcrJob } from '@/ocr/pollJob'
import type { OcrJob } from '@/types/api'

// 03-API-SPEC.md §2 "GET /ocr/jobs/{id}" polling; task brief: 2s interval,
// 60s cap. Uses an injected fake clock/sleep so the state machine's timing
// logic is deterministic and instant (no real setTimeout waits in CI).
function fakeClock() {
  let elapsed = 0
  return {
    now: () => elapsed,
    sleep: async (ms: number) => {
      elapsed += ms
    },
  }
}

describe('pollOcrJob', () => {
  it('resolves immediately when the job has already succeeded on the first fetch', async () => {
    const job: OcrJob = { id: 'j1', attachment_ids: ['a1'], status: 'succeeded' }
    const fetchJob = vi.fn().mockResolvedValue(job)
    const clock = fakeClock()

    const result = await pollOcrJob(fetchJob, { now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'succeeded', job })
    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('polls at the configured interval until the job transitions to succeeded', async () => {
    const statuses: OcrJob['status'][] = ['queued', 'running', 'running', 'succeeded']
    const fetchJob = vi.fn().mockImplementation(async () => ({
      id: 'j1',
      attachment_ids: [],
      status: statuses.shift() as OcrJob['status'],
    }))
    const clock = fakeClock()

    const result = await pollOcrJob(fetchJob, { intervalMs: 2000, timeoutMs: 60000, now: clock.now, sleep: clock.sleep })

    expect(result.status).toBe('succeeded')
    expect(fetchJob).toHaveBeenCalledTimes(4)
  })

  it('stops as soon as the job status is failed, without waiting for another interval', async () => {
    const job: OcrJob = { id: 'j1', attachment_ids: [], status: 'failed', error: 'OCR_PROVIDER_DOWN' }
    const fetchJob = vi.fn().mockResolvedValue(job)
    const clock = fakeClock()

    const result = await pollOcrJob(fetchJob, { now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'failed', job })
    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('gives up with a timeout result after the 60s cap, at the 2s interval (30 polls)', async () => {
    const fetchJob = vi.fn().mockResolvedValue({ id: 'j1', attachment_ids: [], status: 'running' } satisfies OcrJob)
    const clock = fakeClock()

    const result = await pollOcrJob(fetchJob, { intervalMs: 2000, timeoutMs: 60000, now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'timeout' })
    expect(fetchJob).toHaveBeenCalledTimes(30)
  })

  it('respects custom interval/timeout options', async () => {
    const fetchJob = vi.fn().mockResolvedValue({ id: 'j1', attachment_ids: [], status: 'queued' } satisfies OcrJob)
    const clock = fakeClock()

    const result = await pollOcrJob(fetchJob, { intervalMs: 500, timeoutMs: 2000, now: clock.now, sleep: clock.sleep })

    expect(result).toEqual({ status: 'timeout' })
    expect(fetchJob).toHaveBeenCalledTimes(4)
  })
})

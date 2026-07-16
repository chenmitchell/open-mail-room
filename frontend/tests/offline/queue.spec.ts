// 06-UI-UX.md §2 "離線佇列". Uses fake-indexeddb so this exercises the real
// `idb` open/put/getAll/delete calls, not a hand-rolled mock of IndexedDB.
import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { __resetDbForTests } from '@/offline/db'
import {
  clearRegistrations,
  countRegistrations,
  enqueueRegistration,
  flushRegistrations,
  listRegistrations,
  removeRegistration,
} from '@/offline/queue'

function fakeBlob(text: string): Blob {
  return new Blob([text], { type: 'image/jpeg' })
}

describe('offline queue (idb, fake-indexeddb)', () => {
  beforeEach(async () => {
    await __resetDbForTests()
    await clearRegistrations()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('enqueue/list/count/remove a registration round-trips through IndexedDB', async () => {
    expect(await countRegistrations()).toBe(0)

    const record = await enqueueRegistration({
      photos: [
        { photoId: 'p1', blob: fakeBlob('a'), filename: 'a.jpg', mime: 'image/jpeg', barcodeHint: '123' },
      ],
    })

    expect(await countRegistrations()).toBe(1)
    const all = await listRegistrations()
    expect(all).toHaveLength(1)
    expect(all[0].id).toBe(record.id)
    expect(all[0].photos[0].barcodeHint).toBe('123')
    expect(all[0].photos[0].blob).toBeInstanceOf(Blob)

    await removeRegistration(record.id)
    expect(await countRegistrations()).toBe(0)
  })

  it('preserves insertion order across multiple queued registrations', async () => {
    const first = await enqueueRegistration({ photos: [] })
    const second = await enqueueRegistration({ photos: [] })
    const all = await listRegistrations()
    expect(all.map((r) => r.id)).toEqual([first.id, second.id])
  })

  describe('flushRegistrations', () => {
    it('uploads photos + creates an OCR job per registration, then drains the queue on success', async () => {
      await enqueueRegistration({
        photos: [{ photoId: 'p1', blob: fakeBlob('a'), filename: 'a.jpg', mime: 'image/jpeg', barcodeHint: null }],
      })
      await enqueueRegistration({
        photos: [{ photoId: 'p2', blob: fakeBlob('b'), filename: 'b.jpg', mime: 'image/jpeg', barcodeHint: null }],
      })

      const uploadPhotos = vi.fn().mockImplementation(async (photos: { photoId: string }[]) =>
        photos.map((p) => `att-${p.photoId}`),
      )
      const createOcrJob = vi.fn().mockImplementation(async (attachmentIds: string[]) => ({
        id: `job-${attachmentIds[0]}`,
      }))

      const result = await flushRegistrations({ uploadPhotos, createOcrJob })

      expect(result.succeeded).toHaveLength(2)
      expect(result.failed).toHaveLength(0)
      expect(await countRegistrations()).toBe(0)
      expect(uploadPhotos).toHaveBeenCalledTimes(2)
      // Both queued registrations had barcodeHint: null, so the hints map is empty.
      expect(createOcrJob).toHaveBeenCalledWith(['att-p1'], {})
      expect(createOcrJob).toHaveBeenCalledWith(['att-p2'], {})
    })

    it('carries each photo barcodeHint through to createOcrJob, keyed by its resolved attachment id (M2-R1 contract gap #3)', async () => {
      await enqueueRegistration({
        photos: [
          { photoId: 'p1', blob: fakeBlob('a'), filename: 'a.jpg', mime: 'image/jpeg', barcodeHint: '9988776655' },
          { photoId: 'p2', blob: fakeBlob('b'), filename: 'b.jpg', mime: 'image/jpeg', barcodeHint: null },
        ],
      })

      const uploadPhotos = vi.fn().mockImplementation(async (photos: { photoId: string }[]) =>
        photos.map((p) => `att-${p.photoId}`),
      )
      const createOcrJob = vi.fn().mockResolvedValue({ id: 'job-1' })

      const result = await flushRegistrations({ uploadPhotos, createOcrJob })

      expect(result.succeeded).toHaveLength(1)
      expect(createOcrJob).toHaveBeenCalledWith(['att-p1', 'att-p2'], { 'att-p1': '9988776655' })
    })

    it('leaves a failed registration queued for the next flush and reports its error', async () => {
      await enqueueRegistration({
        photos: [{ photoId: 'p1', blob: fakeBlob('a'), filename: 'a.jpg', mime: 'image/jpeg', barcodeHint: null }],
      })

      const uploadPhotos = vi.fn().mockRejectedValue(new Error('offline / server unreachable'))
      const createOcrJob = vi.fn()

      const result = await flushRegistrations({ uploadPhotos, createOcrJob })

      expect(result.succeeded).toHaveLength(0)
      expect(result.failed).toHaveLength(1)
      expect(result.failed[0].error).toContain('offline')
      expect(await countRegistrations()).toBe(1)
      expect(createOcrJob).not.toHaveBeenCalled()
    })

    it('processes remaining registrations even when an earlier one fails', async () => {
      const ok = await enqueueRegistration({
        photos: [{ photoId: 'good', blob: fakeBlob('a'), filename: 'a.jpg', mime: 'image/jpeg', barcodeHint: null }],
      })
      const bad = await enqueueRegistration({
        photos: [{ photoId: 'bad', blob: fakeBlob('b'), filename: 'b.jpg', mime: 'image/jpeg', barcodeHint: null }],
      })

      const uploadPhotos = vi.fn().mockImplementation(async (photos: { photoId: string }[]) => {
        if (photos[0].photoId === 'bad') throw new Error('server error')
        return photos.map((p) => `att-${p.photoId}`)
      })
      const createOcrJob = vi.fn().mockResolvedValue({ id: 'job-good' })

      // enqueue order was `ok` then `bad`; flushRegistrations processes in
      // that order and must not let bad's failure stop ok from succeeding.
      const result = await flushRegistrations({ uploadPhotos, createOcrJob })
      expect(result.succeeded.map((s) => s.registrationId)).toEqual([ok.id])
      expect(result.failed.map((f) => f.registrationId)).toEqual([bad.id])
      const remaining = await listRegistrations()
      expect(remaining.map((r) => r.id)).toEqual([bad.id])
    })

    it('is a no-op that succeeds trivially when the queue is empty', async () => {
      const result = await flushRegistrations({ uploadPhotos: vi.fn(), createOcrJob: vi.fn() })
      expect(result).toEqual({ succeeded: [], failed: [] })
    })
  })
})

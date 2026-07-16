// Offline capture queue (06-UI-UX.md §2). When the counter takes photos with
// no network, the photos + whatever form data was already typed are kept
// here; on reconnect, flushRegistrations() uploads them and creates the OCR
// job(s), then removes them from the queue. It deliberately does NOT auto
// POST /items — 04-AI-OCR.md §1 "人工確認才入庫" is a hard invariant, so a
// reconnect only gets a queued item as far as "ready to confirm" (its OCR
// job now exists and the counter can find/confirm it like any other job).
import { getDb, STORE_NAME } from './db'

export interface PendingPhoto {
  photoId: string
  blob: Blob
  filename: string
  mime: string
  /** Result of the client-side ZXing scan done at capture time (04 §1: 條碼優先). */
  barcodeHint: string | null
}

export interface PendingRegistration {
  id: string
  createdAt: number
  photos: PendingPhoto[]
  /** Any manually-typed fields the counter already had (e.g. a hand-written recipient) — optional. */
  note?: string
}

function makeLocalId(): string {
  // crypto.randomUUID is available in browsers + Node 18+/jsdom's polyfill;
  // fall back to a timestamp+random string so this never throws in an older
  // test environment.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// `Date.now()` only has millisecond resolution — two photos captured (or two
// registrations enqueued in a fast test) within the same millisecond get an
// identical `createdAt`, and `listRegistrations`' sort-by-createdAt then
// falls back to IndexedDB's own key order, which is alphabetical by the
// random UUID `id` — i.e. effectively random, not insertion order. This
// counter makes `createdAt` strictly increasing across calls within the same
// session so insertion order is always preserved, while staying numerically
// close enough to `Date.now()` that `new Date(createdAt)` is still accurate
// to the millisecond for display purposes.
let lastTimestampMs = 0
let sameMsTiebreak = 0

function monotonicCreatedAt(): number {
  const now = Date.now()
  if (now === lastTimestampMs) {
    sameMsTiebreak += 1
  } else {
    lastTimestampMs = now
    sameMsTiebreak = 0
  }
  return now + sameMsTiebreak / 1000
}

export async function enqueueRegistration(
  input: Omit<PendingRegistration, 'id' | 'createdAt'>,
): Promise<PendingRegistration> {
  const record: PendingRegistration = {
    id: makeLocalId(),
    createdAt: monotonicCreatedAt(),
    ...input,
  }
  const db = await getDb()
  await db.put(STORE_NAME, record)
  return record
}

export async function listRegistrations(): Promise<PendingRegistration[]> {
  const db = await getDb()
  const all = await db.getAll(STORE_NAME)
  return (all as PendingRegistration[]).sort((a, b) => a.createdAt - b.createdAt)
}

export async function removeRegistration(id: string): Promise<void> {
  const db = await getDb()
  await db.delete(STORE_NAME, id)
}

export async function countRegistrations(): Promise<number> {
  const db = await getDb()
  return db.count(STORE_NAME)
}

export async function clearRegistrations(): Promise<void> {
  const db = await getDb()
  await db.clear(STORE_NAME)
}

export interface FlushHandlers {
  /** Uploads this registration's photos, returns their attachment ids (03 §2 POST /uploads). */
  uploadPhotos: (photos: PendingPhoto[]) => Promise<string[]>
  /**
   * Creates the OCR job for the uploaded group (03 §2 POST /ocr/jobs).
   * `barcodeHints` (M2-R1 contract gap #3, offline-flush half: "離線 flush
   * 路徑也要帶") maps attachment id -> the barcode ZXing scanned at capture
   * time (`PendingPhoto.barcodeHint`) -- carried through the offline queue
   * so a reconnect-and-resubmit gets the same "barcode known, save tokens"
   * behaviour as the online path, not just a same-session capture.
   */
  createOcrJob: (attachmentIds: string[], barcodeHints?: Record<string, string>) => Promise<{ id: string }>
}

export interface FlushResult {
  succeeded: Array<{ registrationId: string; jobId: string }>
  failed: Array<{ registrationId: string; error: string }>
}

/**
 * Attempts to send every queued registration. Entries that fail (still
 * offline, server error, ...) are left in the queue for the next flush —
 * this function never throws, it reports per-entry outcomes so the caller
 * (the offline-queue store) can update the visible queue count either way.
 */
export async function flushRegistrations(handlers: FlushHandlers): Promise<FlushResult> {
  const pending = await listRegistrations()
  const result: FlushResult = { succeeded: [], failed: [] }

  for (const registration of pending) {
    try {
      const attachmentIds = await handlers.uploadPhotos(registration.photos)
      const barcodeHints: Record<string, string> = {}
      registration.photos.forEach((photo, index) => {
        const attachmentId = attachmentIds[index]
        if (attachmentId && photo.barcodeHint) {
          barcodeHints[attachmentId] = photo.barcodeHint
        }
      })
      const job = await handlers.createOcrJob(attachmentIds, barcodeHints)
      await removeRegistration(registration.id)
      result.succeeded.push({ registrationId: registration.id, jobId: job.id })
    } catch (err) {
      const message = err instanceof Error ? err.message : '補送失敗,將於下次連線時重試。'
      result.failed.push({ registrationId: registration.id, error: message })
    }
  }

  return result
}

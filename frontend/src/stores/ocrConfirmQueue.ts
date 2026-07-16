// Hand-off between the camera/batch-upload pages and the OCR confirm page.
//
// FE-STABILITY: this used to also carry `photoUrls` — local
// `URL.createObjectURL(blob)` previews handed off from the capture/upload
// pages so OcrConfirmPage could render a left-side photo without a backend
// "download this attachment" endpoint (03-API-SPEC.md didn't document one
// at the time). That was a real production bug: those object URLs only
// live in the tab's memory, so a page refresh or a PWA service-worker
// update (both of which reload the document) invalidated them instantly,
// leaving the confirm page with broken/blank images. The backend contract
// now exposes `GET /api/v1/uploads/{attachment_id}` (cookie-authed, same
// origin), so OcrConfirmPage loads photos straight from the server via
// `attachmentIds` + `getUploadUrl()` (src/api/uploads.ts) instead — nothing
// to revoke, nothing that can go stale on reload.
import { defineStore } from 'pinia'

export interface QueuedOcrJob {
  jobId: string
  attachmentIds: string[]
  barcodeHint: string | null
  /**
   * attachment id -> EXIF capture time (UTC ISO) or null, carried over from
   * `POST /uploads` so the confirm page can show *when the photo was taken*
   * next to each photo. Optional: an offline-queued job replayed later, or a
   * job restored by an older client, simply has no capture times to show.
   */
  capturedAt?: Record<string, string | null>
}

interface OcrConfirmQueueState {
  jobs: QueuedOcrJob[]
}

export const useOcrConfirmQueueStore = defineStore('ocrConfirmQueue', {
  state: (): OcrConfirmQueueState => ({ jobs: [] }),

  getters: {
    current: (state): QueuedOcrJob | undefined => state.jobs[0],
    remaining: (state): number => state.jobs.length,
  },

  actions: {
    push(job: QueuedOcrJob): void {
      this.jobs.push(job)
    },
    /** Removes and returns the job currently at the front of the queue (after it's confirmed/skipped). */
    advance(): QueuedOcrJob | undefined {
      return this.jobs.shift()
    },
    clear(): void {
      this.jobs = []
    },
  },
})

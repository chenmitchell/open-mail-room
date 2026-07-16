// 03-API-SPEC.md §2 「照片與 OCR」: `POST /uploads` multipart, batch <= 30
// photos, returns attachment ids.
//
// This bypasses `apiClient` (src/api/client.ts) deliberately: the task brief
// requires per-file upload progress for the batch upload page (06 §1), and
// `fetch()` has no upload-progress event — only `XMLHttpRequest` does. CSRF
// header / credentials behaviour is duplicated here to match client.ts.
import { ApiError } from './client'
import type { UploadedAttachment } from '@/types/api'

const API_BASE = '/api/v1'
const CSRF_COOKIE_NAME = 'csrf_token'
const CSRF_HEADER_NAME = 'X-CSRF-Token'
const MAX_BATCH_SIZE = 30

function getCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  if (!match) return null
  return decodeURIComponent(match.slice(name.length + 1))
}

export interface UploadPhotoInput {
  /** Stable local id so the caller can correlate progress/results back to a captured photo. */
  localId: string
  blob: Blob
  filename: string
}

export type UploadProgressHandler = (localId: string, fraction: number) => void

/**
 * Uploads a single photo via XHR (for progress events) and resolves to the
 * server-assigned attachment id. Used by uploadPhotos() below, one call per
 * file, so a failure in one photo doesn't abort the rest of the batch (06 §1
 * "逐張進度、失敗重試").
 */
function uploadOne(photo: UploadPhotoInput, onProgress?: UploadProgressHandler): Promise<UploadedAttachment> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('files', photo.blob, photo.filename)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/uploads`)
    xhr.withCredentials = true

    const csrfToken = getCookie(CSRF_COOKIE_NAME)
    if (csrfToken) xhr.setRequestHeader(CSRF_HEADER_NAME, csrfToken)

    xhr.upload.onprogress = (event) => {
      if (!onProgress) return
      const fraction = event.lengthComputable ? event.loaded / event.total : 0
      onProgress(photo.localId, fraction)
    }

    xhr.onerror = () => reject(new ApiError('NETWORK_ERROR', '網路連線異常,請檢查連線後再試。', 0))

    xhr.onload = () => {
      let body: { data?: { attachments?: UploadedAttachment[] }; error?: { code: string; message: string } } | null = null
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        body = null
      }

      if (xhr.status < 200 || xhr.status >= 300 || body?.error) {
        const err = body?.error ?? { code: 'UPLOAD_FAILED', message: xhr.statusText || '上傳失敗' }
        reject(new ApiError(err.code, err.message, xhr.status))
        return
      }

      // POST /uploads always responds with { data: { attachments: [...] } }
      // (app/api/v1/uploads.py `_serialize` wrapped in a list under the
      // "attachments" key), never a bare array/object -- see backend
      // tests/test_uploads.py's `resp.json()["data"]["attachments"][0]`.
      const attachment: UploadedAttachment | undefined = body?.data?.attachments?.[0]
      if (!attachment?.id) {
        reject(new ApiError('UPLOAD_FAILED', '上傳失敗:伺服器未回傳附件編號。', xhr.status))
        return
      }
      onProgress?.(photo.localId, 1)
      resolve(attachment)
    }

    xhr.send(form)
  })
}

export interface UploadPhotosResult {
  /** localId -> attachment id, only for photos that succeeded. */
  attachmentIds: Record<string, string>
  /**
   * attachment id -> EXIF capture time (UTC ISO) or null. Keyed by
   * *attachment* id, not localId, because the confirm page renders photos by
   * attachment id and has no localId to correlate with.
   */
  capturedAt: Record<string, string | null>
  /** localId -> error, for photos that failed (06 §1 "失敗重試" needs to know which). */
  failures: Record<string, ApiError>
}

/**
 * Uploads up to 30 photos (03 §2 batch limit), one HTTP request per photo so
 * progress/retry can be tracked per-file. Failures are collected rather than
 * thrown so the caller can retry just the failed subset.
 */
export async function uploadPhotos(
  photos: UploadPhotoInput[],
  onProgress?: UploadProgressHandler,
): Promise<UploadPhotosResult> {
  if (photos.length > MAX_BATCH_SIZE) {
    throw new ApiError('UPLOAD_TOO_LARGE', `一次最多上傳 ${MAX_BATCH_SIZE} 張照片。`, 400)
  }

  const attachmentIds: Record<string, string> = {}
  const capturedAt: Record<string, string | null> = {}
  const failures: Record<string, ApiError> = {}

  await Promise.all(
    photos.map(async (photo) => {
      try {
        const attachment = await uploadOne(photo, onProgress)
        attachmentIds[photo.localId] = attachment.id
        capturedAt[attachment.id] = attachment.captured_at ?? null
      } catch (err) {
        failures[photo.localId] = err instanceof ApiError ? err : new ApiError('UPLOAD_FAILED', '上傳失敗', 0)
      }
    }),
  )

  return { attachmentIds, capturedAt, failures }
}

/**
 * Same-origin GET /uploads/{attachment_id} URL for an already-uploaded
 * attachment (03-API-SPEC.md contract landed after the original
 * OcrConfirmPage assumption below the ocrConfirmQueue store was written --
 * see that store's comment history). Used directly as an `<img src>`; the
 * browser sends the HttpOnly session cookie automatically since it's a
 * same-origin request, no extra auth wiring needed here. Kept as a pure
 * string builder (mirrors src/api/reports.ts's getExportUrl) so it stays
 * unit-testable without a DOM/network round-trip.
 */
export function getUploadUrl(attachmentId: string): string {
  return `${API_BASE}/uploads/${attachmentId}`
}

export { MAX_BATCH_SIZE }

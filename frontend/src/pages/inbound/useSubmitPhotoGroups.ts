// Shared submit flow for both the photo-capture page and the batch-upload
// page (06 §1): group photos -> if offline, queue them (idb); if online,
// upload each group, create its OCR job, and hand it to the confirm-page
// queue. Factored out so the two pages don't duplicate this branching.
import { uploadPhotos, type UploadProgressHandler } from '@/api/uploads'
import { createOcrJob } from '@/api/ocr'
import { useOfflineQueueStore } from '@/stores/offlineQueue'
import { useOcrConfirmQueueStore } from '@/stores/ocrConfirmQueue'
import { buildBarcodeHints, groupBarcodeHint, groupPhotos, type CapturedPhoto } from './photoGroups'

export interface SubmitPhotoGroupsResult {
  /** Number of item-groups written to the offline queue (network was unavailable). */
  queued: number
  /** Number of OCR jobs successfully created (network was available). */
  jobs: number
}

function isOnline(): boolean {
  return typeof navigator === 'undefined' ? true : navigator.onLine
}

export function useSubmitPhotoGroups() {
  const offlineQueue = useOfflineQueueStore()
  const confirmQueue = useOcrConfirmQueueStore()

  async function submit(
    photos: CapturedPhoto[],
    onProgress?: UploadProgressHandler,
  ): Promise<SubmitPhotoGroupsResult> {
    const groups = groupPhotos(photos)

    if (!isOnline()) {
      for (const group of groups) {
        await offlineQueue.enqueue({
          photos: group.map((p) => ({
            photoId: p.id,
            blob: p.blob,
            filename: p.filename,
            mime: p.blob.type || 'image/jpeg',
            barcodeHint: p.barcodeHint,
          })),
        })
      }
      return { queued: groups.length, jobs: 0 }
    }

    let jobCount = 0
    for (const group of groups) {
      const { attachmentIds, capturedAt, failures } = await uploadPhotos(
        group.map((p) => ({ localId: p.id, blob: p.blob, filename: p.filename })),
        onProgress,
      )
      const firstFailure = Object.values(failures)[0]
      if (firstFailure) throw firstFailure

      const ids = group.map((p) => attachmentIds[p.id]).filter((id): id is string => !!id)
      const job = await createOcrJob(ids, buildBarcodeHints(group, attachmentIds))
      confirmQueue.push({
        jobId: job.id,
        attachmentIds: ids,
        barcodeHint: groupBarcodeHint(group).value,
        capturedAt,
      })
      jobCount += 1
    }
    return { queued: 0, jobs: jobCount }
  }

  return { submit }
}

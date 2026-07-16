// 03-API-SPEC.md §2 「照片與 OCR」endpoints.
import { apiClient } from './client'
import type { OcrDraft, OcrJob } from '@/types/api'

// `POST /ocr/jobs { attachment_ids: [...], barcode_hints?: {...} }` —
// 04-AI-OCR.md §3 "同一件多張照片:多圖一次送同一個 vision 請求...ocr_jobs
// 因此允許一個 job 綁多個 attachment". One call = one item's photo group; the
// batch/photo pages call this once per group (see pages/inbound/photoGroups.ts).
//
// `barcodeHints` (M2-R1 contract gap #3: "barcode_hints 前端從未送出") maps
// attachment id -> the barcode value ZXing already scanned client-side for
// that specific photo (src/barcode/scan.ts) -- 04 §4's "條碼已取得單號時...
// 可降低輸出 token" mechanism was dead code without this, since the backend
// only ever sees `barcode_known` as true when this field is actually
// populated (app/api/v1/ocr_jobs.py).
export function createOcrJob(
  attachmentIds: string[],
  barcodeHints?: Record<string, string>,
): Promise<OcrJob> {
  return apiClient.post<OcrJob>('/ocr/jobs', {
    attachment_ids: attachmentIds,
    ...(barcodeHints && Object.keys(barcodeHints).length > 0 ? { barcode_hints: barcodeHints } : {}),
  })
}

// `GET /ocr/jobs/{id}` — polled every 2s, capped at 60s (see src/ocr/pollJob.ts).
export function getOcrJob(id: string): Promise<OcrJob> {
  return apiClient.get<OcrJob>(`/ocr/jobs/${id}`)
}

// `GET /ocr/jobs/{id}/draft` — only meaningful once status === 'succeeded'.
export function getOcrDraft(id: string): Promise<OcrDraft> {
  return apiClient.get<OcrDraft>(`/ocr/jobs/${id}/draft`)
}

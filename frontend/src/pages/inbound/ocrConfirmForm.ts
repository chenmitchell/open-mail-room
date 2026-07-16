// Bridges an OCR draft (04-AI-OCR.md §3 extraction JSON) into the same
// InboundFormState used by the manual-registration page (inboundForm.ts) —
// the OCR confirm page is really "手動登記 pre-filled from OCR + a barcode",
// so it reuses that form's validation/payload logic instead of duplicating
// it (06 §1 "欄位可改" — after prefill, it's just an editable form).
import type { Carrier, OcrDraftFields } from '@/types/api'
import { createEmptyInboundForm, type InboundFormState } from './inboundForm'

// 04 §1: "條碼優先,AI 補位...單號若條碼已取得,AI 結果不覆蓋".
export function resolveTrackingNo(barcodeHint: string | null, ocrTrackingNo: string | null): string {
  return (barcodeHint ?? ocrTrackingNo ?? '').trim()
}

/** Best-effort match of the OCR carrier slug guess against the known carrier list. */
function resolveCarrierId(carrierGuess: string | null, carriers: Carrier[]): string {
  if (!carrierGuess) return ''
  const match = carriers.find((c) => c.slug === carrierGuess)
  return match?.id ?? ''
}

export function createFormFromOcrDraft(
  fields: OcrDraftFields,
  barcodeHint: string | null,
  carriers: Carrier[] = [],
): InboundFormState {
  const base = createEmptyInboundForm()
  return {
    ...base,
    trackingNo: resolveTrackingNo(barcodeHint, fields.tracking_no),
    carrierId: resolveCarrierId(fields.carrier_guess, carriers),
    senderName: (fields.sender_name ?? '').trim(),
    senderOrg: (fields.sender_org ?? '').trim(),
    recipientNameRaw: (fields.recipient_name ?? '').trim(),
    // mail_type isn't extracted by the OCR prompt (04 §3) — the counter
    // always picks it explicitly, same as manual registration.
  }
}

// 04 §3 only exposes a single overall `confidence` (0~1), not a per-field
// score. ASSUMPTION (flag for backend/reviewer): until the backend exposes
// per-field confidence, every non-null AI-derived field is treated as
// "low confidence" together whenever the job's overall confidence is below
// the threshold — the tracking number is EXCLUDED whenever it came from the
// barcode scan (barcode reads are exact, never a confidence guess).
export const LOW_CONFIDENCE_THRESHOLD = 0.7

export type OcrConfirmFieldKey =
  | 'trackingNo'
  | 'carrierId'
  | 'senderName'
  | 'senderOrg'
  | 'recipientNameRaw'

export function lowConfidenceFields(
  fields: OcrDraftFields,
  form: InboundFormState,
  barcodeHint: string | null,
  threshold = LOW_CONFIDENCE_THRESHOLD,
): OcrConfirmFieldKey[] {
  if (fields.confidence >= threshold) return []

  const flagged: OcrConfirmFieldKey[] = []
  if (form.trackingNo && !barcodeHint) flagged.push('trackingNo')
  if (form.carrierId) flagged.push('carrierId')
  if (form.senderName) flagged.push('senderName')
  if (form.senderOrg) flagged.push('senderOrg')
  if (form.recipientNameRaw) flagged.push('recipientNameRaw')
  return flagged
}

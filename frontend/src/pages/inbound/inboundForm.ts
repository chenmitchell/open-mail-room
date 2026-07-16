// Pure form-state + validation for the 手動登記頁 (06 §1 / 01 §3 收件必填/選填).
// Kept out of the .vue file so it is directly unit-testable without mounting
// a component, router, or i18n instance.
import type { CreateMailItemPayload, MailType, RefrigerationType } from '@/types/api'

export interface InboundFormState {
  mailType: MailType | ''
  recipientNameRaw: string
  recipientEmployeeId: string | null
  // 部門件: the department this item is routed to (its contact becomes the
  // recipient employee). null for a normal personal item.
  departmentId: string | null
  trackingNo: string
  carrierId: string
  // UX-VISUAL task B: free-text shown/required when the carrier dropdown's
  // current selection is the seeded "其他" carrier (scripts/seed.py
  // slug='other') -- see src/composables/useOtherOption.ts. No backend
  // schema change, so this never reaches CreateMailItemPayload as its own
  // field; inboundFormToPayload merges it into `note` instead.
  otherCarrierName: string
  senderName: string
  senderOrg: string
  isConfidential: boolean
  isCod: boolean
  codAmount: string
  refrigeration: RefrigerationType
  sizeNote: string
  note: string
}

export function createEmptyInboundForm(): InboundFormState {
  return {
    mailType: '',
    recipientNameRaw: '',
    recipientEmployeeId: null,
    departmentId: null,
    trackingNo: '',
    carrierId: '',
    otherCarrierName: '',
    senderName: '',
    senderOrg: '',
    isConfidential: false,
    isCod: false,
    codAmount: '',
    refrigeration: 'none',
    sizeNote: '',
    note: '',
  }
}

// Extra context the pure form-state doesn't otherwise have: whether the
// currently-selected carrierId resolves to the "其他" option. Callers
// (InboundRegisterPage.vue) derive this from the loaded carrier list via
// isOtherSelected() and pass it in explicitly, keeping this module free of
// any API/carrier-list dependency so it stays trivially unit-testable.
export interface InboundFormContext {
  carrierIsOther?: boolean
  /** i18n'd "承運商(其他)" prefix for the merged note line; falls back to
   * the zh-TW copy so callers that don't pass one (e.g. existing tests)
   * keep working unchanged. */
  otherCarrierNotePrefix?: string
}

// i18n keys, not literal messages, so the caller can translate for either
// locale — matches the task's "驗證與錯誤顯示(具體描述,aria-describedby)"
// requirement: each key names exactly what's wrong (missing vs. too long vs.
// not a number), never a generic "invalid input".
export type InboundFormErrors = Partial<Record<keyof InboundFormState, string>>

const MAX_TEXT_LENGTH = 200
const MAX_NOTE_LENGTH = 1000

export function validateInboundForm(
  form: InboundFormState,
  ctx: InboundFormContext = {},
): InboundFormErrors {
  const errors: InboundFormErrors = {}

  if (!form.mailType) {
    errors.mailType = 'inbound.errors.mailTypeRequired'
  }

  if (ctx.carrierIsOther && !form.otherCarrierName.trim()) {
    errors.otherCarrierName = 'otherField.errors.carrierRequired'
  }

  const recipient = form.recipientNameRaw.trim()
  if (!recipient) {
    errors.recipientNameRaw = 'inbound.errors.recipientRequired'
  } else if (recipient.length > MAX_TEXT_LENGTH) {
    errors.recipientNameRaw = 'inbound.errors.recipientTooLong'
  }

  if (form.trackingNo.trim().length > MAX_TEXT_LENGTH) {
    errors.trackingNo = 'inbound.errors.trackingTooLong'
  }

  if (form.senderName.trim().length > MAX_TEXT_LENGTH) {
    errors.senderName = 'inbound.errors.senderNameTooLong'
  }

  if (form.senderOrg.trim().length > MAX_TEXT_LENGTH) {
    errors.senderOrg = 'inbound.errors.senderOrgTooLong'
  }

  if (form.isCod) {
    const trimmed = form.codAmount.trim()
    if (!trimmed) {
      errors.codAmount = 'inbound.errors.codAmountRequired'
    } else {
      const amount = Number(trimmed)
      if (!Number.isFinite(amount) || amount <= 0) {
        errors.codAmount = 'inbound.errors.codAmountInvalid'
      }
    }
  }

  if (form.note.trim().length > MAX_NOTE_LENGTH) {
    errors.note = 'inbound.errors.noteTooLong'
  }

  return errors
}

// UX-VISUAL task B: no backend schema change for the "其他" free-text value
// -- it's merged into the plain `note` field as a clearly-marked extra line
// ("承運商(其他):<value>"), ahead of whatever the user already typed into
// note, so neither gets silently dropped.
function mergeOtherIntoNote(baseNote: string, ctx: InboundFormContext, otherValue: string): string | undefined {
  const lines: string[] = []
  const trimmedOther = otherValue.trim()
  if (ctx.carrierIsOther && trimmedOther) {
    const prefix = ctx.otherCarrierNotePrefix ?? '承運商(其他)'
    lines.push(`${prefix}:${trimmedOther}`)
  }
  const trimmedBase = baseNote.trim()
  if (trimmedBase) lines.push(trimmedBase)
  return lines.length ? lines.join('\n') : undefined
}

export function inboundFormToPayload(
  form: InboundFormState,
  ctx: InboundFormContext = {},
): CreateMailItemPayload {
  if (!form.mailType) {
    throw new Error('inboundFormToPayload called with an invalid (unvalidated) form')
  }
  return {
    mail_type: form.mailType,
    recipient_name_raw: form.recipientNameRaw.trim(),
    recipient_employee_id: form.recipientEmployeeId,
    department_id: form.departmentId || undefined,
    tracking_no: form.trackingNo.trim() || undefined,
    carrier_id: form.carrierId || undefined,
    sender_name: form.senderName.trim() || undefined,
    sender_org: form.senderOrg.trim() || undefined,
    is_confidential: form.isConfidential,
    is_cod: form.isCod,
    cod_amount: form.isCod ? Number(form.codAmount) : undefined,
    refrigeration: form.refrigeration,
    size_note: form.sizeNote.trim() || undefined,
    note: mergeOtherIntoNote(form.note, ctx, form.otherCarrierName),
  }
}

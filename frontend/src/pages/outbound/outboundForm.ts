// Pure form-state + validation for the 交寄頁 create form (01 §2.2 / §3
// 「交寄欄位」, 06 §1 「交寄」). Kept out of the .vue file so it is directly
// unit-testable without mounting a component, router, or i18n instance —
// same convention as src/pages/inbound/inboundForm.ts.
import type { CreateOutboundPayload, OutboundPayment } from '@/types/api'

export interface OutboundFormState {
  applicantNameRaw: string
  applicantEmployeeId: string | null
  departmentId: string
  toName: string
  toOrg: string
  toAddress: string
  toPhone: string
  carrierId: string
  // UX-VISUAL task B: free-text shown/required when the carrier dropdown's
  // current selection is the seeded "其他" carrier -- see
  // src/composables/useOtherOption.ts / inboundForm.ts's twin field for the
  // full rationale. Merged into `note` by outboundFormToPayload, never sent
  // as its own field (no backend schema change).
  otherCarrierName: string
  payment: OutboundPayment | ''
  cost: string
  note: string
}

export function createEmptyOutboundForm(): OutboundFormState {
  return {
    applicantNameRaw: '',
    applicantEmployeeId: null,
    departmentId: '',
    toName: '',
    toOrg: '',
    toAddress: '',
    toPhone: '',
    carrierId: '',
    otherCarrierName: '',
    payment: '',
    cost: '',
    note: '',
  }
}

// See inboundForm.ts's InboundFormContext for why this is passed in
// explicitly rather than derived here.
export interface OutboundFormContext {
  carrierIsOther?: boolean
  otherCarrierNotePrefix?: string
}

// i18n keys, not literal messages — see inboundForm.ts for why.
export type OutboundFormErrors = Partial<Record<keyof OutboundFormState, string>>

const MAX_TEXT_LENGTH = 200
const MAX_ADDRESS_LENGTH = 500
const MAX_NOTE_LENGTH = 1000

export function validateOutboundForm(
  form: OutboundFormState,
  ctx: OutboundFormContext = {},
): OutboundFormErrors {
  const errors: OutboundFormErrors = {}

  const toName = form.toName.trim()
  if (!toName) {
    errors.toName = 'outbound.errors.toNameRequired'
  } else if (toName.length > MAX_TEXT_LENGTH) {
    errors.toName = 'outbound.errors.toNameTooLong'
  }

  if (ctx.carrierIsOther && !form.otherCarrierName.trim()) {
    errors.otherCarrierName = 'otherField.errors.carrierRequired'
  }

  if (form.toOrg.trim().length > MAX_TEXT_LENGTH) {
    errors.toOrg = 'outbound.errors.toOrgTooLong'
  }

  if (form.toAddress.trim().length > MAX_ADDRESS_LENGTH) {
    errors.toAddress = 'outbound.errors.toAddressTooLong'
  }

  if (form.toPhone.trim().length > MAX_TEXT_LENGTH) {
    errors.toPhone = 'outbound.errors.toPhoneTooLong'
  }

  if (form.note.trim().length > MAX_NOTE_LENGTH) {
    errors.note = 'outbound.errors.noteTooLong'
  }

  const cost = form.cost.trim()
  if (cost) {
    const amount = Number(cost)
    if (!Number.isFinite(amount) || amount <= 0) {
      errors.cost = 'outbound.errors.costInvalid'
    }
  }

  return errors
}

// UX-VISUAL task B: see inboundForm.ts's twin helper for the full rationale
// (no backend schema change, merge into `note` ahead of the user's own text).
function mergeOtherIntoNote(baseNote: string, ctx: OutboundFormContext, otherValue: string): string | undefined {
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

export function outboundFormToPayload(
  form: OutboundFormState,
  ctx: OutboundFormContext = {},
): CreateOutboundPayload {
  const toName = form.toName.trim()
  if (!toName) {
    throw new Error('outboundFormToPayload called with an invalid (unvalidated) form')
  }
  return {
    applicant_employee_id: form.applicantEmployeeId,
    department_id: form.departmentId || undefined,
    to_name: toName,
    to_org: form.toOrg.trim() || undefined,
    to_address: form.toAddress.trim() || undefined,
    to_phone: form.toPhone.trim() || undefined,
    carrier_id: form.carrierId || undefined,
    payment: form.payment || undefined,
    cost: form.cost.trim() ? Number(form.cost.trim()) : undefined,
    note: mergeOtherIntoNote(form.note, ctx, form.otherCarrierName),
  }
}

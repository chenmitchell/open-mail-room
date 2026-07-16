import { describe, expect, it } from 'vitest'
import {
  createFormFromOcrDraft,
  lowConfidenceFields,
  resolveTrackingNo,
} from '@/pages/inbound/ocrConfirmForm'
import type { Carrier, OcrDraftFields } from '@/types/api'

function draft(overrides: Partial<OcrDraftFields> = {}): OcrDraftFields {
  return {
    tracking_no: null,
    carrier_guess: null,
    sender_name: null,
    sender_org: null,
    sender_phone: null,
    recipient_name: null,
    recipient_dept_hint: null,
    is_handwritten: false,
    confidence: 0.9,
    ...overrides,
  }
}

const carriers: Carrier[] = [
  { id: 'c-tcat', name: '黑貓', slug: 'tcat', kind: 'courier', is_active: true },
]

describe('resolveTrackingNo — 04 §1 條碼優先,AI 結果不覆蓋', () => {
  it('prefers the barcode value even when the OCR draft also has a tracking number', () => {
    expect(resolveTrackingNo('9988776655', '1111111111')).toBe('9988776655')
  })

  it('falls back to the OCR value when there is no barcode', () => {
    expect(resolveTrackingNo(null, '1111111111')).toBe('1111111111')
  })

  it('is an empty string when neither source has a value', () => {
    expect(resolveTrackingNo(null, null)).toBe('')
  })
})

describe('createFormFromOcrDraft', () => {
  it('prefills sender/recipient text fields, trimmed', () => {
    const form = createFormFromOcrDraft(
      draft({ sender_name: '  王大明  ', sender_org: '  某公司  ', recipient_name: ' 陳小華 ' }),
      null,
      [],
    )
    expect(form.senderName).toBe('王大明')
    expect(form.senderOrg).toBe('某公司')
    expect(form.recipientNameRaw).toBe('陳小華')
    // mail_type is never produced by the OCR prompt (04 §3) — always left for the counter to pick.
    expect(form.mailType).toBe('')
  })

  it('resolves carrier_guess to a known carrier id by slug', () => {
    const form = createFormFromOcrDraft(draft({ carrier_guess: 'tcat' }), null, carriers)
    expect(form.carrierId).toBe('c-tcat')
  })

  it('leaves carrierId empty when the guessed slug is unknown', () => {
    const form = createFormFromOcrDraft(draft({ carrier_guess: 'some_unknown_carrier' }), null, carriers)
    expect(form.carrierId).toBe('')
  })

  it('uses the barcode hint for trackingNo over the draft value', () => {
    const form = createFormFromOcrDraft(draft({ tracking_no: '000' }), '9988776655', [])
    expect(form.trackingNo).toBe('9988776655')
  })
})

describe('lowConfidenceFields', () => {
  it('flags nothing when the job confidence is at/above the threshold', () => {
    const fields = draft({ sender_name: '王大明', confidence: 0.9 })
    const form = createFormFromOcrDraft(fields, null, [])
    expect(lowConfidenceFields(fields, form, null)).toEqual([])
  })

  it('flags only the non-empty AI-derived fields when confidence is below the threshold', () => {
    const fields = draft({ sender_name: '王大明', confidence: 0.4 }) // sender_org stays null
    const form = createFormFromOcrDraft(fields, null, [])
    const flagged = lowConfidenceFields(fields, form, null)
    expect(flagged).toContain('senderName')
    expect(flagged).not.toContain('senderOrg') // was empty, nothing to flag
  })

  it('never flags trackingNo when its value came from the barcode scan (barcode reads are exact, not a guess)', () => {
    const fields = draft({ tracking_no: '000', confidence: 0.2 })
    const form = createFormFromOcrDraft(fields, '9988776655', [])
    const flagged = lowConfidenceFields(fields, form, '9988776655')
    expect(flagged).not.toContain('trackingNo')
  })

  it('flags trackingNo when its (low-confidence) value came from the OCR draft itself', () => {
    const fields = draft({ tracking_no: '000', confidence: 0.2 })
    const form = createFormFromOcrDraft(fields, null, [])
    const flagged = lowConfidenceFields(fields, form, null)
    expect(flagged).toContain('trackingNo')
  })

  it('respects a custom threshold', () => {
    const fields = draft({ sender_name: '王大明', confidence: 0.75 })
    const form = createFormFromOcrDraft(fields, null, [])
    expect(lowConfidenceFields(fields, form, null, 0.9)).toContain('senderName')
    expect(lowConfidenceFields(fields, form, null, 0.5)).toEqual([])
  })
})

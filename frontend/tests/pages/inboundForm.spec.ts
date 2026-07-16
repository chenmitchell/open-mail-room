import { describe, expect, it } from 'vitest'
import {
  createEmptyInboundForm,
  inboundFormToPayload,
  validateInboundForm,
} from '@/pages/inbound/inboundForm'

describe('validateInboundForm', () => {
  it('requires mailType and recipientNameRaw', () => {
    const errors = validateInboundForm(createEmptyInboundForm())
    expect(errors.mailType).toBe('inbound.errors.mailTypeRequired')
    expect(errors.recipientNameRaw).toBe('inbound.errors.recipientRequired')
  })

  it('passes with just the required fields filled in', () => {
    const form = { ...createEmptyInboundForm(), mailType: 'parcel' as const, recipientNameRaw: '王小明' }
    expect(validateInboundForm(form)).toEqual({})
  })

  it('rejects a recipient name over the length limit', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'letter' as const,
      recipientNameRaw: 'a'.repeat(201),
    }
    expect(validateInboundForm(form).recipientNameRaw).toBe('inbound.errors.recipientTooLong')
  })

  it('requires a positive codAmount when isCod is on', () => {
    const base = { ...createEmptyInboundForm(), mailType: 'parcel' as const, recipientNameRaw: '王小明', isCod: true }

    expect(validateInboundForm({ ...base, codAmount: '' }).codAmount).toBe(
      'inbound.errors.codAmountRequired',
    )
    expect(validateInboundForm({ ...base, codAmount: '0' }).codAmount).toBe(
      'inbound.errors.codAmountInvalid',
    )
    expect(validateInboundForm({ ...base, codAmount: 'not-a-number' }).codAmount).toBe(
      'inbound.errors.codAmountInvalid',
    )
    expect(validateInboundForm({ ...base, codAmount: '350' }).codAmount).toBeUndefined()
  })

  it('does not require codAmount when isCod is off', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
      isCod: false,
    }
    expect(validateInboundForm(form).codAmount).toBeUndefined()
  })

  it('rejects a note over the length limit', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'letter' as const,
      recipientNameRaw: '王小明',
      note: 'a'.repeat(1001),
    }
    expect(validateInboundForm(form).note).toBe('inbound.errors.noteTooLong')
  })

  // UX-VISUAL task B: 承運商下拉選到「其他」-> otherCarrierName 必填.
  it('requires otherCarrierName when the carrier dropdown resolved to "其他"', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
      otherCarrierName: '',
    }
    expect(validateInboundForm(form, { carrierIsOther: true }).otherCarrierName).toBe(
      'otherField.errors.carrierRequired',
    )
    expect(
      validateInboundForm({ ...form, otherCarrierName: '  ' }, { carrierIsOther: true })
        .otherCarrierName,
    ).toBe('otherField.errors.carrierRequired')
    expect(
      validateInboundForm({ ...form, otherCarrierName: '順風貨運' }, { carrierIsOther: true })
        .otherCarrierName,
    ).toBeUndefined()
  })

  it('does not require otherCarrierName when the carrier is not "其他"', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
    }
    expect(validateInboundForm(form, { carrierIsOther: false }).otherCarrierName).toBeUndefined()
    expect(validateInboundForm(form).otherCarrierName).toBeUndefined()
  })
})

describe('inboundFormToPayload', () => {
  it('maps a valid form to the POST /items payload shape (03 §2)', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '  王小明  ',
      recipientEmployeeId: 'emp-1',
      trackingNo: '  1234567890  ',
      carrierId: 'carrier-1',
      isCod: true,
      codAmount: '500',
    }
    const payload = inboundFormToPayload(form)
    expect(payload).toMatchObject({
      mail_type: 'parcel',
      recipient_name_raw: '王小明',
      recipient_employee_id: 'emp-1',
      tracking_no: '1234567890',
      carrier_id: 'carrier-1',
      is_cod: true,
      cod_amount: 500,
    })
  })

  it('throws if called with an unvalidated (empty mailType) form — guards against skipping validation', () => {
    expect(() => inboundFormToPayload(createEmptyInboundForm())).toThrow()
  })

  // UX-VISUAL task B: no backend schema change -- the "其他" free-text value
  // is merged into `note` as a clearly-marked extra line, ahead of whatever
  // the user already typed into note (neither gets silently dropped).
  it('merges the "其他承運商" value into note as a marked line when carrierIsOther is true', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
      otherCarrierName: '順風貨運',
      note: '易碎品',
    }
    const payload = inboundFormToPayload(form, {
      carrierIsOther: true,
      otherCarrierNotePrefix: '承運商(其他)',
    })
    expect(payload.note).toBe('承運商(其他):順風貨運\n易碎品')
  })

  it('does not touch note when carrierIsOther is false, even if otherCarrierName has a stale value', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
      otherCarrierName: '順風貨運',
      note: '易碎品',
    }
    const payload = inboundFormToPayload(form, { carrierIsOther: false })
    expect(payload.note).toBe('易碎品')
  })

  it('falls back to the zh-TW note prefix when no otherCarrierNotePrefix is passed', () => {
    const form = {
      ...createEmptyInboundForm(),
      mailType: 'parcel' as const,
      recipientNameRaw: '王小明',
      otherCarrierName: '順風貨運',
    }
    const payload = inboundFormToPayload(form, { carrierIsOther: true })
    expect(payload.note).toBe('承運商(其他):順風貨運')
  })
})

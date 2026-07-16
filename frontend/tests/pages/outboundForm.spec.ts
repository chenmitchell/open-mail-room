import { describe, expect, it } from 'vitest'
import {
  createEmptyOutboundForm,
  outboundFormToPayload,
  validateOutboundForm,
} from '@/pages/outbound/outboundForm'

describe('validateOutboundForm', () => {
  it('requires toName', () => {
    const errors = validateOutboundForm(createEmptyOutboundForm())
    expect(errors.toName).toBe('outbound.errors.toNameRequired')
  })

  it('passes with just the required field filled in', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明' }
    expect(validateOutboundForm(form)).toEqual({})
  })

  it('rejects a recipient name over the length limit', () => {
    const form = { ...createEmptyOutboundForm(), toName: 'a'.repeat(201) }
    expect(validateOutboundForm(form).toName).toBe('outbound.errors.toNameTooLong')
  })

  it('rejects an address over the length limit', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明', toAddress: 'a'.repeat(501) }
    expect(validateOutboundForm(form).toAddress).toBe('outbound.errors.toAddressTooLong')
  })

  it('rejects a note over the length limit', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明', note: 'a'.repeat(1001) }
    expect(validateOutboundForm(form).note).toBe('outbound.errors.noteTooLong')
  })

  it('allows an empty cost (optional field)', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明', cost: '' }
    expect(validateOutboundForm(form).cost).toBeUndefined()
  })

  it('rejects a zero or negative cost', () => {
    const base = { ...createEmptyOutboundForm(), toName: '王小明' }
    expect(validateOutboundForm({ ...base, cost: '0' }).cost).toBe('outbound.errors.costInvalid')
    expect(validateOutboundForm({ ...base, cost: '-5' }).cost).toBe('outbound.errors.costInvalid')
    expect(validateOutboundForm({ ...base, cost: 'not-a-number' }).cost).toBe('outbound.errors.costInvalid')
    expect(validateOutboundForm({ ...base, cost: '120' }).cost).toBeUndefined()
  })

  // UX-VISUAL task B: 承運商下拉選到「其他」-> otherCarrierName 必填.
  it('requires otherCarrierName when the carrier dropdown resolved to "其他"', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明', otherCarrierName: '' }
    expect(validateOutboundForm(form, { carrierIsOther: true }).otherCarrierName).toBe(
      'otherField.errors.carrierRequired',
    )
    expect(
      validateOutboundForm({ ...form, otherCarrierName: '  ' }, { carrierIsOther: true })
        .otherCarrierName,
    ).toBe('otherField.errors.carrierRequired')
    expect(
      validateOutboundForm({ ...form, otherCarrierName: '順風貨運' }, { carrierIsOther: true })
        .otherCarrierName,
    ).toBeUndefined()
  })

  it('does not require otherCarrierName when the carrier is not "其他"', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明' }
    expect(validateOutboundForm(form, { carrierIsOther: false }).otherCarrierName).toBeUndefined()
    expect(validateOutboundForm(form).otherCarrierName).toBeUndefined()
  })
})

describe('outboundFormToPayload', () => {
  it('maps a valid form to the POST /outbound payload shape (03 §2)', () => {
    const form = {
      ...createEmptyOutboundForm(),
      applicantEmployeeId: 'emp-1',
      departmentId: 'dept-1',
      toName: '  客戶 A  ',
      toOrg: 'ACME',
      toAddress: '台北市信義區',
      toPhone: '0912345678',
      carrierId: 'carrier-1',
      payment: 'company' as const,
      cost: '350',
      note: '易碎品',
    }
    const payload = outboundFormToPayload(form)
    expect(payload).toEqual({
      applicant_employee_id: 'emp-1',
      department_id: 'dept-1',
      to_name: '客戶 A',
      to_org: 'ACME',
      to_address: '台北市信義區',
      to_phone: '0912345678',
      carrier_id: 'carrier-1',
      payment: 'company',
      cost: 350,
      note: '易碎品',
    })
  })

  it('omits optional fields that were left blank', () => {
    const form = { ...createEmptyOutboundForm(), toName: '王小明' }
    const payload = outboundFormToPayload(form)
    expect(payload).toEqual({
      applicant_employee_id: null,
      department_id: undefined,
      to_name: '王小明',
      to_org: undefined,
      to_address: undefined,
      to_phone: undefined,
      carrier_id: undefined,
      payment: undefined,
      cost: undefined,
      note: undefined,
    })
  })

  it('throws if called with an unvalidated (empty toName) form — guards against skipping validation', () => {
    expect(() => outboundFormToPayload(createEmptyOutboundForm())).toThrow()
  })

  // UX-VISUAL task B: no backend schema change -- the "其他" free-text value
  // is merged into `note` as a clearly-marked extra line, ahead of whatever
  // the user already typed into note (neither gets silently dropped).
  it('merges the "其他承運商" value into note as a marked line when carrierIsOther is true', () => {
    const form = {
      ...createEmptyOutboundForm(),
      toName: '客戶 A',
      otherCarrierName: '順風貨運',
      note: '易碎品',
    }
    const payload = outboundFormToPayload(form, {
      carrierIsOther: true,
      otherCarrierNotePrefix: '承運商(其他)',
    })
    expect(payload.note).toBe('承運商(其他):順風貨運\n易碎品')
  })

  it('does not touch note when carrierIsOther is false, even if otherCarrierName has a stale value', () => {
    const form = {
      ...createEmptyOutboundForm(),
      toName: '客戶 A',
      otherCarrierName: '順風貨運',
      note: '易碎品',
    }
    const payload = outboundFormToPayload(form, { carrierIsOther: false })
    expect(payload.note).toBe('易碎品')
  })
})

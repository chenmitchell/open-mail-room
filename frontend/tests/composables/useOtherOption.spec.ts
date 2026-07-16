import { describe, expect, it } from 'vitest'
import { isOtherSelected } from '@/composables/useOtherOption'

// UX-VISUAL task B: shared detection for the carrier / mail_type / payment
// dropdowns' "選其他 -> 展開必填輸入" behaviour. Carrier options loaded from
// GET /carriers carry a real `slug` (backend/scripts/seed.py seeds
// slug='other', name='其他'); other dropdowns are fixed enums with no slug,
// so a literal value/label match is also accepted.
describe('isOtherSelected', () => {
  const carrierOptions = [
    { value: 'c1', label: '中華郵政掛號/包裹', slug: 'chunghwa_post' },
    { value: 'c2', label: '其他', slug: 'other' },
  ]

  it('returns true when the selected option carries slug="other"', () => {
    expect(isOtherSelected('c2', carrierOptions)).toBe(true)
  })

  it('returns false for a normal carrier selection', () => {
    expect(isOtherSelected('c1', carrierOptions)).toBe(false)
  })

  it('returns false when nothing is selected yet', () => {
    expect(isOtherSelected('', carrierOptions)).toBe(false)
  })

  it('returns false when the value does not match any option', () => {
    expect(isOtherSelected('does-not-exist', carrierOptions)).toBe(false)
  })

  it('falls back to matching value or label for enum-style dropdowns without a slug', () => {
    const enumOptions = [
      { value: 'letter', label: '信件' },
      { value: 'other', label: '其他' },
    ]
    expect(isOtherSelected('other', enumOptions)).toBe(true)
    expect(isOtherSelected('letter', enumOptions)).toBe(false)
  })

  it('matches the English "Other" label for the en locale', () => {
    const enumOptions = [
      { value: 'letter', label: 'Letter' },
      { value: 'misc', label: 'Other' },
    ]
    expect(isOtherSelected('misc', enumOptions)).toBe(true)
  })
})

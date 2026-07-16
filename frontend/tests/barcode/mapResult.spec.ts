import { describe, expect, it } from 'vitest'
import {
  dedupeBarcodeHints,
  pickPrimaryBarcodeHint,
  resolveGroupBarcodeHint,
  toBarcodeHint,
} from '@/barcode/mapResult'

// 04-AI-OCR.md §1 "條碼優先,AI 補位" / 06 §2 "ZXing 即時掃碼". These are the
// pure mapping/priority functions the camera + batch pages rely on; the
// actual @zxing/browser call (src/barcode/scan.ts) is a thin, untested
// adapter around them.
describe('toBarcodeHint', () => {
  it('maps a raw zxing-style result into a BarcodeHint', () => {
    expect(toBarcodeHint({ text: '1234567890', formatName: 'CODE_128' })).toEqual({
      value: '1234567890',
      format: 'CODE_128',
    })
  })

  it('trims whitespace around the decoded text', () => {
    expect(toBarcodeHint({ text: '  ABC123  ', formatName: 'QR_CODE' })).toEqual({
      value: 'ABC123',
      format: 'QR_CODE',
    })
  })

  it('returns null for an empty/whitespace-only result', () => {
    expect(toBarcodeHint({ text: '', formatName: 'CODE_128' })).toBeNull()
    expect(toBarcodeHint({ text: '   ', formatName: 'CODE_128' })).toBeNull()
  })
})

describe('dedupeBarcodeHints', () => {
  it('keeps only the first occurrence of each distinct value', () => {
    const hints = [
      { value: 'A1', format: 'CODE_128' },
      { value: 'A1', format: 'CODE_128' },
      { value: 'B2', format: 'QR_CODE' },
    ]
    expect(dedupeBarcodeHints(hints)).toEqual([
      { value: 'A1', format: 'CODE_128' },
      { value: 'B2', format: 'QR_CODE' },
    ])
  })
})

describe('pickPrimaryBarcodeHint', () => {
  it('returns null when there are no hints', () => {
    expect(pickPrimaryBarcodeHint([])).toBeNull()
  })

  it('returns the single hint when there is only one', () => {
    const hint = { value: 'A1', format: 'CODE_128' }
    expect(pickPrimaryBarcodeHint([hint])).toEqual(hint)
  })

  it('prefers a 1D tracking-style barcode over a QR code on the same photo', () => {
    const qr = { value: 'https://example.com/promo', format: 'QR_CODE' }
    const oneD = { value: '9988776655', format: 'CODE_128' }
    expect(pickPrimaryBarcodeHint([qr, oneD])).toEqual(oneD)
    // Order in the input shouldn't matter.
    expect(pickPrimaryBarcodeHint([oneD, qr])).toEqual(oneD)
  })

  it('falls back to the QR code when that is the only symbol found', () => {
    const qr = { value: 'QR-ONLY-VALUE', format: 'QR_CODE' }
    expect(pickPrimaryBarcodeHint([qr])).toEqual(qr)
  })
})

describe('resolveGroupBarcodeHint', () => {
  it('returns null/no-conflict when no photo in the group had a barcode', () => {
    expect(resolveGroupBarcodeHint([null, null])).toEqual({ hint: null, conflict: false })
  })

  it('returns the single shared value with no conflict when all photos agree', () => {
    const hint = { value: '123', format: 'CODE_128' }
    expect(resolveGroupBarcodeHint([hint, null, hint])).toEqual({ hint, conflict: false })
  })

  // 04 §3: "兩張照片同欄位值衝突時,該欄位標警示,由櫃台在確認頁裁決".
  it('flags a conflict when two photos in the same group scan to different values', () => {
    const first = { value: '111', format: 'CODE_128' }
    const second = { value: '222', format: 'CODE_128' }
    const result = resolveGroupBarcodeHint([first, second])
    expect(result.conflict).toBe(true)
    expect(result.hint).toEqual(first)
  })
})

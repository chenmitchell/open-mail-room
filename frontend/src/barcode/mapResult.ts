// Pure mapping/priority logic for ZXing barcode results — kept dependency-
// free from the actual @zxing/browser/@zxing/library runtime so it is
// directly unit-testable under jsdom (no camera/canvas needed). The thin
// runtime wrapper that actually calls into zxing lives in src/barcode/scan.ts
// and is not unit-tested itself (04 §1 / 06 §1: 條碼優先, 1D+QR).
import type { BarcodeHint } from '@/types/api'

// Mirrors the subset of zxing's `Result` we need. Callers pass
// `result.getText()` / `BarcodeFormat[result.getBarcodeFormat()]` in — see
// scan.ts — so this module never has to import @zxing/library's types.
export interface RawBarcodeResult {
  text: string
  formatName: string
}

/** Normalises a raw zxing result into our BarcodeHint shape. */
export function toBarcodeHint(raw: RawBarcodeResult): BarcodeHint | null {
  const value = raw.text?.trim()
  if (!value) return null
  return { value, format: raw.formatName }
}

/** De-dupes by value, keeping the first occurrence's format. */
export function dedupeBarcodeHints(hints: BarcodeHint[]): BarcodeHint[] {
  const seen = new Map<string, BarcodeHint>()
  for (const hint of hints) {
    if (!seen.has(hint.value)) seen.set(hint.value, hint)
  }
  return [...seen.values()]
}

// 04 §1 "條碼優先,AI 補位": when a single photo yields multiple candidate
// barcodes (rare, but the 1D+QR reader can pick up more than one symbol),
// prefer a 1D tracking-style barcode over a QR code, since 1D codes on
// Taiwan carrier labels are almost always the tracking number while QR codes
// are more often carrier-internal/promo codes. Ties keep scan order.
const QR_FORMATS = new Set(['QR_CODE'])

export function pickPrimaryBarcodeHint(hints: BarcodeHint[]): BarcodeHint | null {
  const unique = dedupeBarcodeHints(hints)
  if (unique.length === 0) return null
  const oneD = unique.find((h) => !QR_FORMATS.has(h.format))
  return oneD ?? unique[0]
}

export interface GroupBarcodeResolution {
  hint: BarcodeHint | null
  /** true when two photos in the same group scanned to different, non-empty values. */
  conflict: boolean
}

/**
 * Resolves the barcode hint to use for a whole photo group (e.g. two photos
 * of the same parcel). 04 §3's multi-photo merge rule: "兩張照片同欄位值
 * 衝突時,該欄位標警示,由櫃台在確認頁裁決" — applied here to the
 * barcode-derived tracking number specifically.
 */
export function resolveGroupBarcodeHint(hints: Array<BarcodeHint | null>): GroupBarcodeResolution {
  const present = hints.filter((h): h is BarcodeHint => h !== null)
  if (present.length === 0) return { hint: null, conflict: false }
  const distinctValues = new Set(present.map((h) => h.value))
  if (distinctValues.size > 1) {
    return { hint: present[0], conflict: true }
  }
  return { hint: present[0], conflict: false }
}

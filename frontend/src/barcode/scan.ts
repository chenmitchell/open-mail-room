// Thin runtime wrapper around @zxing/browser / @zxing/library (04-AI-OCR.md
// §1 "前端 @zxing/browser 先掃 1D/QR 條碼"). Deliberately NOT unit-tested —
// it only calls into the third-party decoder and DOM APIs (camera/canvas)
// that jsdom cannot meaningfully simulate. All the decision logic (mapping a
// raw result, picking/merging hints) lives in src/barcode/mapResult.ts and
// *is* unit-tested; this file is kept as a small, obviously-correct adapter.
//
// M2-R1 suggestion (adopted): `@zxing/browser` + `@zxing/library` together
// are ~462KB, and every page that captures a photo (CameraCapture.vue,
// BatchUploadPage.vue, PhotoRegisterPage.vue) statically imported this
// module — pulling zxing into those pages' route chunk even before the
// camera/scanner is actually used. Both zxing packages are now dynamically
// imported *inside* the two exported functions below instead of at module
// top-level, so bundlers split them into their own async chunk that only
// loads on first actual use (first captured photo / first live-scan start),
// not as part of the page's initial synchronous bundle.
import { toBarcodeHint } from './mapResult'
import type { BarcodeHint } from '@/types/api'
import type { BrowserMultiFormatReader as BrowserMultiFormatReaderType } from '@zxing/browser'

let sharedReaderPromise: Promise<BrowserMultiFormatReaderType> | null = null

async function getReader(): Promise<BrowserMultiFormatReaderType> {
  if (!sharedReaderPromise) {
    sharedReaderPromise = import('@zxing/browser').then(
      ({ BrowserMultiFormatReader }) => new BrowserMultiFormatReader(),
    )
  }
  return sharedReaderPromise
}

/**
 * Decodes a single captured photo (Blob) for a 1D/QR barcode. Returns null
 * when no barcode is found — a normal outcome (e.g. a plain letter has none),
 * not an error; capture must never be blocked by a failed scan.
 */
export async function scanBarcodeFromBlob(blob: Blob): Promise<BarcodeHint | null> {
  const [reader, { BarcodeFormat, NotFoundException }] = await Promise.all([
    getReader(),
    import('@zxing/library'),
  ])
  const url = URL.createObjectURL(blob)
  try {
    const result = await reader.decodeFromImageUrl(url)
    return toBarcodeHint({
      text: result.getText(),
      formatName: BarcodeFormat[result.getBarcodeFormat()],
    })
  } catch (err) {
    if (err instanceof NotFoundException) return null
    // Any other decode failure (checksum/format mismatch, corrupt image) also
    // degrades to "no barcode" — AI/manual entry remains the fallback.
    return null
  } finally {
    URL.revokeObjectURL(url)
  }
}

export interface LiveScanControls {
  stop: () => void
}

/**
 * Starts continuous scanning against a live <video> element (06 §2
 * getUserMedia path — "即時掃碼框"). `onDetect` only fires when a *new*
 * value is read, so holding a code steady in frame doesn't spam repeated
 * aria-live announcements.
 */
export async function startLiveScan(
  videoElement: HTMLVideoElement,
  onDetect: (hint: BarcodeHint) => void,
): Promise<LiveScanControls> {
  const [reader, { BarcodeFormat }] = await Promise.all([getReader(), import('@zxing/library')])
  let lastValue: string | null = null
  const controls = await reader.decodeFromVideoDevice(undefined, videoElement, (result) => {
    if (!result) return
    const hint = toBarcodeHint({
      text: result.getText(),
      formatName: BarcodeFormat[result.getBarcodeFormat()],
    })
    if (!hint || hint.value === lastValue) return
    lastValue = hint.value
    onDetect(hint)
  })
  return { stop: () => controls.stop() }
}

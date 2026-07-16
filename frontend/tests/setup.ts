// Global vitest setup. Kept intentionally minimal — component specs that need
// i18n/router/pinia install what they need locally via @vue/test-utils.
//
// Two jsdom gaps patched here (both real jsdom limitations, not app bugs):
//
// 1. jsdom does not implement `URL.createObjectURL` / `URL.revokeObjectURL`
//    at all (the properties don't exist), so any spec that mounts a page
//    calling them (OcrConfirmPage, BatchUploadPage, PhotoRegisterPage,
//    barcode/scan.ts) throws, and `vi.spyOn(URL, 'revokeObjectURL')` fails
//    with "revokeObjectURL does not exist" because spyOn requires the
//    property to already be present. No-op polyfills are sufficient since
//    tests never need the resulting blob: URL to resolve to real image data.
//
// 2. jsdom's `Blob` is a distinct class from Node's built-in `Blob`, and
//    Node's global `structuredClone` (used internally by fake-indexeddb's
//    `cloneValueForInsertion`, see node_modules/fake-indexeddb/build/*/lib/
//    cloneValueForInsertion.js) does not recognize jsdom's Blob as a
//    cloneable platform object — it round-trips as `{}`. Swapping in
//    Node's native `Blob`/`File` (from `node:buffer`) for the test globals
//    fixes structuredClone while remaining spec-compatible (arrayBuffer(),
//    text(), size, type, slice() all present) for every other spec that
//    constructs a Blob.
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'

globalThis.Blob = NodeBlob as unknown as typeof Blob
globalThis.File = NodeFile as unknown as typeof File

if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = (() => 'blob:mock-url') as typeof URL.createObjectURL
}
if (typeof URL.revokeObjectURL !== 'function') {
  URL.revokeObjectURL = (() => {}) as typeof URL.revokeObjectURL
}

export {}

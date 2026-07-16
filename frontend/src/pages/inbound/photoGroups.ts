// Pure photo-grouping logic shared by the camera page's "連拍模式(一張=一件)
// / ＋加拍同件" and the batch-upload confirm step's "框選多張合併為一件"
// (06 §1). Kept out of the .vue files so grouping/merge/payload-building is
// directly unit-testable without mounting components.

export interface CapturedPhoto {
  id: string
  groupId: string
  blob: Blob
  filename: string
  /** Result of the client-side ZXing scan for this specific photo (04 §1). */
  barcodeHint: string | null
}

let idCounter = 0
export function nextLocalId(prefix: string): string {
  idCounter += 1
  return `${prefix}-${idCounter}`
}

/** Appends a photo as its own new group — one photo = one item (連拍模式預設). */
export function addAsNewGroup(
  photos: CapturedPhoto[],
  blob: Blob,
  filename: string,
  barcodeHint: string | null = null,
): CapturedPhoto[] {
  const photo: CapturedPhoto = {
    id: nextLocalId('photo'),
    groupId: nextLocalId('group'),
    blob,
    filename,
    barcodeHint,
  }
  return [...photos, photo]
}

/** Appends a photo into the same group as the most recently added photo ("＋加拍同件"). */
export function addToLastGroup(
  photos: CapturedPhoto[],
  blob: Blob,
  filename: string,
  barcodeHint: string | null = null,
): CapturedPhoto[] {
  const lastGroupId = photos.length > 0 ? photos[photos.length - 1].groupId : nextLocalId('group')
  const photo: CapturedPhoto = {
    id: nextLocalId('photo'),
    groupId: lastGroupId,
    blob,
    filename,
    barcodeHint,
  }
  return [...photos, photo]
}

export function removePhoto(photos: CapturedPhoto[], photoId: string): CapturedPhoto[] {
  return photos.filter((p) => p.id !== photoId)
}

/**
 * Reassigns every photo in `photoIds` to a single shared group (the first
 * selected photo's group, unless the caller overrides it), implementing the
 * batch confirm step's "框選多張合併為一件" (06 §1).
 */
export function mergeIntoGroup(
  photos: CapturedPhoto[],
  photoIds: string[],
  targetGroupId?: string,
): CapturedPhoto[] {
  if (photoIds.length < 2 && !targetGroupId) return photos
  const idSet = new Set(photoIds)
  const first = photos.find((p) => idSet.has(p.id))
  const groupId = targetGroupId ?? first?.groupId
  if (!groupId) return photos
  return photos.map((p) => (idSet.has(p.id) ? { ...p, groupId } : p))
}

/** Groups photos by groupId, preserving first-seen group order and photo order within each group. */
export function groupPhotos(photos: CapturedPhoto[]): CapturedPhoto[][] {
  const order: string[] = []
  const byGroup = new Map<string, CapturedPhoto[]>()
  for (const photo of photos) {
    if (!byGroup.has(photo.groupId)) {
      byGroup.set(photo.groupId, [])
      order.push(photo.groupId)
    }
    byGroup.get(photo.groupId)!.push(photo)
  }
  return order.map((groupId) => byGroup.get(groupId)!)
}

export interface OcrJobPayload {
  groupId: string
  attachment_ids: string[]
}

/**
 * Builds one `POST /ocr/jobs` payload per group (04 §3: "ocr_jobs...允許一
 * 個 job 綁多個 attachment"), mapping each photo's local id to the
 * server-assigned attachment id via `attachmentIdByPhotoId`. Photos whose
 * upload hasn't completed yet (no entry in the map) are skipped — the caller
 * is expected to only call this once every photo in the group has uploaded.
 */
export function buildOcrJobPayloads(
  photos: CapturedPhoto[],
  attachmentIdByPhotoId: Record<string, string>,
): OcrJobPayload[] {
  return groupPhotos(photos).map((group) => ({
    groupId: group[0].groupId,
    attachment_ids: group.map((p) => attachmentIdByPhotoId[p.id]).filter((id): id is string => !!id),
  }))
}

/**
 * Resolves the single barcode hint to carry forward for a group, applying
 * 04 §3's conflict rule at the group level (see also
 * src/barcode/mapResult.ts#resolveGroupBarcodeHint for the underlying
 * pairwise logic) — returns the first non-null hint plus whether more than
 * one distinct value was seen across the group's photos.
 */
export function groupBarcodeHint(group: CapturedPhoto[]): { value: string | null; conflict: boolean } {
  const values = group.map((p) => p.barcodeHint).filter((v): v is string => !!v)
  if (values.length === 0) return { value: null, conflict: false }
  const distinct = new Set(values)
  return { value: values[0], conflict: distinct.size > 1 }
}

/**
 * Builds the `POST /ocr/jobs` `barcode_hints` payload (M2-R1 contract gap
 * #3: "barcode_hints 前端從未送出") — maps each photo's *server-assigned*
 * attachment id to the barcode value ZXing scanned for that specific photo,
 * skipping photos with no scan result and photos whose upload hasn't
 * resolved to an attachment id yet. One entry per photo (not per group):
 * the backend keys `barcode_hints` by attachment_id (app/api/v1/ocr_jobs.py),
 * so a multi-photo group with per-photo scans carries all of them through,
 * not just the single value src/barcode/mapResult.ts#resolveGroupBarcodeHint
 * picks for *display* purposes.
 */
export function buildBarcodeHints(
  group: CapturedPhoto[],
  attachmentIdByPhotoId: Record<string, string>,
): Record<string, string> {
  const hints: Record<string, string> = {}
  for (const photo of group) {
    const attachmentId = attachmentIdByPhotoId[photo.id]
    if (attachmentId && photo.barcodeHint) {
      hints[attachmentId] = photo.barcodeHint
    }
  }
  return hints
}

import { describe, expect, it } from 'vitest'
import {
  addAsNewGroup,
  addToLastGroup,
  buildBarcodeHints,
  buildOcrJobPayloads,
  groupBarcodeHint,
  groupPhotos,
  mergeIntoGroup,
  removePhoto,
} from '@/pages/inbound/photoGroups'

function fakeBlob(): Blob {
  return new Blob(['x'], { type: 'image/jpeg' })
}

// 06-UI-UX.md §1/§2: "連拍模式(一張=一件)與「＋加拍同件」" (photo page) and
// "確認頁可框選多張合併為一件" (batch page) — both reduce to grouping
// CapturedPhoto[] by groupId, tested here in isolation from any component.
describe('addAsNewGroup / addToLastGroup', () => {
  it('每張新照片預設各自成為一件 (連拍模式)', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'b.jpg')
    const groups = groupPhotos(photos)
    expect(groups).toHaveLength(2)
    expect(groups[0]).toHaveLength(1)
    expect(groups[1]).toHaveLength(1)
  })

  it('"＋加拍同件" 把新照片加進最後一組', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'b.jpg') // starts a second item
    photos = addToLastGroup(photos, fakeBlob(), 'b2.jpg')

    const groups = groupPhotos(photos)
    expect(groups).toHaveLength(2)
    expect(groups[0]).toHaveLength(2)
    expect(groups[0].map((p) => p.filename)).toEqual(['a.jpg', 'a2.jpg'])
    expect(groups[1]).toHaveLength(2)
    expect(groups[1].map((p) => p.filename)).toEqual(['b.jpg', 'b2.jpg'])
  })

  it('addToLastGroup on an empty list still produces a usable single group', () => {
    const photos = addToLastGroup([], fakeBlob(), 'solo.jpg')
    expect(groupPhotos(photos)).toHaveLength(1)
  })
})

describe('removePhoto', () => {
  it('removes just the targeted photo, leaving its group intact for the rest', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')
    const toRemove = photos[0].id
    photos = removePhoto(photos, toRemove)
    expect(photos).toHaveLength(1)
    expect(photos[0].filename).toBe('a2.jpg')
  })
})

describe('mergeIntoGroup — 框選多張合併為一件', () => {
  it('reassigns every selected photo to the first selected photo\'s group', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'b.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'c.jpg')
    expect(groupPhotos(photos)).toHaveLength(3)

    const [a, b] = photos
    photos = mergeIntoGroup(photos, [a.id, b.id])

    const groups = groupPhotos(photos)
    expect(groups).toHaveLength(2)
    const merged = groups.find((g) => g.length === 2)!
    expect(merged.map((p) => p.filename).sort()).toEqual(['a.jpg', 'b.jpg'])
  })

  it('is a no-op when fewer than two photos are selected and no explicit target group is given', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'b.jpg')
    const unchanged = mergeIntoGroup(photos, [photos[0].id])
    expect(unchanged).toEqual(photos)
  })
})

describe('buildOcrJobPayloads', () => {
  it('builds one payload per group, mapping local photo ids to uploaded attachment ids', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')
    photos = addAsNewGroup(photos, fakeBlob(), 'b.jpg')

    const attachmentIdByPhotoId: Record<string, string> = {
      [photos[0].id]: 'att-1',
      [photos[1].id]: 'att-2',
      [photos[2].id]: 'att-3',
    }

    const payloads = buildOcrJobPayloads(photos, attachmentIdByPhotoId)
    expect(payloads).toHaveLength(2)
    expect(payloads[0].attachment_ids).toEqual(['att-1', 'att-2'])
    expect(payloads[1].attachment_ids).toEqual(['att-3'])
  })

  it('skips photos whose upload has not produced an attachment id yet', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')

    const attachmentIdByPhotoId: Record<string, string> = { [photos[0].id]: 'att-1' }
    const payloads = buildOcrJobPayloads(photos, attachmentIdByPhotoId)
    expect(payloads[0].attachment_ids).toEqual(['att-1'])
  })
})

describe('groupBarcodeHint', () => {
  it('returns null with no conflict when no photo in the group scanned a barcode', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')
    expect(groupBarcodeHint(photos)).toEqual({ value: null, conflict: false })
  })

  it('surfaces the shared barcode value when every scanned photo agrees', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg', '123')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg', '123')
    expect(groupBarcodeHint(photos)).toEqual({ value: '123', conflict: false })
  })

  it('flags a conflict when photos in the same group scan to different barcode values', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg', '123')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg', '456')
    const result = groupBarcodeHint(photos)
    expect(result.conflict).toBe(true)
    expect(result.value).toBe('123')
  })
})

// M2-R1 contract gap #3: "barcode_hints 前端從未送出" — createOcrJob's
// payload is built from this, keyed by attachment_id (not groupId), so the
// backend's `barcode_known` prompt shortcut (04 §4) actually fires.
describe('buildBarcodeHints', () => {
  it('maps each scanned photo to its resolved attachment id', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg', '111')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg', null)

    const attachmentIdByPhotoId: Record<string, string> = {
      [photos[0].id]: 'att-1',
      [photos[1].id]: 'att-2',
    }

    expect(buildBarcodeHints(photos, attachmentIdByPhotoId)).toEqual({ 'att-1': '111' })
  })

  it('is empty when no photo in the group scanned a barcode', () => {
    let photos = addAsNewGroup([], fakeBlob(), 'a.jpg')
    photos = addToLastGroup(photos, fakeBlob(), 'a2.jpg')
    const attachmentIdByPhotoId: Record<string, string> = {
      [photos[0].id]: 'att-1',
      [photos[1].id]: 'att-2',
    }
    expect(buildBarcodeHints(photos, attachmentIdByPhotoId)).toEqual({})
  })

  it('skips a scanned photo whose upload has not resolved to an attachment id yet', () => {
    const photos = addAsNewGroup([], fakeBlob(), 'a.jpg', '111')
    expect(buildBarcodeHints(photos, {})).toEqual({})
  })
})

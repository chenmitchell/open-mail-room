import { afterEach, describe, expect, it, vi } from 'vitest'
import { createOcrJob } from '@/api/ocr'

// M2-R1 contract gap #3: "barcode_hints 前端從未送出" — createOcrJob only
// ever sent attachment_ids, so the backend's barcode_known prompt shortcut
// (04-AI-OCR.md §4) was dead code. This locks in the request body shape.
function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('createOcrJob (03-API-SPEC.md §2 POST /ocr/jobs)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends barcode_hints alongside attachment_ids when hints are given', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: 'job-1', attachment_ids: ['att-1'], status: 'queued' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createOcrJob(['att-1'], { 'att-1': '9988776655' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      attachment_ids: ['att-1'],
      barcode_hints: { 'att-1': '9988776655' },
    })
  })

  it('omits barcode_hints entirely when there are none (no photo scanned a barcode)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: 'job-1', attachment_ids: ['att-1'], status: 'queued' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createOcrJob(['att-1'])

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string)
    expect(body).toEqual({ attachment_ids: ['att-1'] })
    expect(body.barcode_hints).toBeUndefined()
  })

  it('omits barcode_hints when given an empty hints object', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: 'job-1', attachment_ids: ['att-1'], status: 'queued' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createOcrJob(['att-1'], {})

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ attachment_ids: ['att-1'] })
  })
})

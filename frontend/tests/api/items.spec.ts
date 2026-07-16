import { afterEach, describe, expect, it, vi } from 'vitest'
import { listItems, pickupItem } from '@/api/items'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('items api (mocked backend, 03-API-SPEC.md §2)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listItems builds the querystring from filters and unwraps { data, meta }', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: [{ id: '1', item_no: 'IN-20260709-0001' }],
        error: null,
        meta: { total: 1, page: 1, size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listItems({ status: 'notified', q: '王小明', page: 2, size: 20 })

    expect(result.items).toHaveLength(1)
    expect(result.meta).toEqual({ total: 1, page: 1, size: 20 })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toContain('/api/v1/items?')
    expect(url).toContain('status=notified')
    expect(url).toContain('q=%E7%8E%8B%E5%B0%8F%E6%98%8E')
    expect(url).toContain('page=2')
  })

  it('listItems omits undefined/empty filters entirely', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: [], error: null, meta: { total: 0, page: 1, size: 20 } }))
    vi.stubGlobal('fetch', fetchMock)

    await listItems({ q: undefined, status: undefined })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/items')
  })

  it('pickupItem posts to /items/{id}/pickup with the method/signature/code body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: '1', item_no: 'IN-20260709-0001', status: 'picked_up' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await pickupItem('1', {
      method: 'signature',
      picked_up_by_name: '王小明',
      signature_png_base64: 'iVBORw0K...',
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/items/1/pickup')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({
      method: 'signature',
      picked_up_by_name: '王小明',
    })
  })

  it('surfaces ITEM_ALREADY_PICKED as an ApiError (03 §4 error codes)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: null, error: { code: 'ITEM_ALREADY_PICKED', message: '此件已被領取' } }, 409),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      pickupItem('1', { method: 'pickup_code', picked_up_by_name: '王小明', pickup_code: 'ABCD1234' }),
    ).rejects.toMatchObject({ code: 'ITEM_ALREADY_PICKED' })
  })
})

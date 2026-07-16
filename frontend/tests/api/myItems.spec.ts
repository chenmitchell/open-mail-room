import { afterEach, describe, expect, it, vi } from 'vitest'
import { listMyItems } from '@/api/myItems'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('myItems api (mocked backend, ASSUMPTION GET /me/items — see src/api/myItems.ts)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listMyItems GETs /me/items and unwraps { data, meta }', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: [{ id: '1', item_no: 'IN-20260709-0001', status: 'notified' }],
        error: null,
        meta: { total: 1, page: 1, size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listMyItems({ size: 20 })

    expect(result.items).toHaveLength(1)
    expect(result.meta).toEqual({ total: 1, page: 1, size: 20 })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/me/items?size=20')
  })

  it('omits undefined filters entirely', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: [], error: null, meta: { total: 0, page: 1, size: 20 } }))
    vi.stubGlobal('fetch', fetchMock)

    await listMyItems({})
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/me/items')
  })
})

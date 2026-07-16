import { afterEach, describe, expect, it, vi } from 'vitest'
import { lookupByPickupCode } from '@/api/pickup'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('pickup api (mocked backend, M1-R1 blocking #3)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lookupByPickupCode posts to /pickup/lookup with the code and unwraps the result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          employee: { id: 'e1', name: '王小明', department_id: 'd1', department_name: '行銷部' },
          items: [{ id: 'i1', item_no: 'IN-20260709-0001', status: 'notified' }],
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await lookupByPickupCode('ABCD1234')

    expect(result.employee.name).toBe('王小明')
    // The backend deliberately never returns pickup_code in this response
    // (M1-R1 blocking #3); the type doesn't even declare the field.
    expect(result.employee).not.toHaveProperty('pickup_code')
    expect(result.items).toHaveLength(1)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/pickup/lookup')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ pickup_code: 'ABCD1234' })
  })

  it('surfaces PICKUP_CODE_INVALID as an ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { data: null, error: { code: 'PICKUP_CODE_INVALID', message: 'no match' } },
        422,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(lookupByPickupCode('WRONGCODE')).rejects.toMatchObject({
      code: 'PICKUP_CODE_INVALID',
    })
  })

  it('surfaces PICKUP_CODE_RATE_LIMITED as an ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { data: null, error: { code: 'PICKUP_CODE_RATE_LIMITED', message: 'too many attempts' } },
        429,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(lookupByPickupCode('ABCD1234')).rejects.toMatchObject({
      code: 'PICKUP_CODE_RATE_LIMITED',
    })
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient, ApiError, onUnauthorized } from '@/api/client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    onUnauthorized(() => {})
    document.cookie = 'csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('unwraps { data, error: null } into the resolved value', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ data: { id: 1 }, error: null })))
    const result = await apiClient.get<{ id: number }>('/items/1')
    expect(result).toEqual({ id: 1 })
  })

  it('throws an ApiError carrying the backend error code/message on { error }', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ data: null, error: { code: 'ITEM_ALREADY_PICKED', message: '此件已被領取' } }, 409),
        ),
    )
    await expect(apiClient.get('/items/1')).rejects.toMatchObject({
      code: 'ITEM_ALREADY_PICKED',
      message: '此件已被領取',
    })
  })

  it('invokes the registered 401 handler and still throws an ApiError', async () => {
    const handler = vi.fn()
    onUnauthorized(handler)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ data: null, error: { code: 'AUTH_INVALID', message: 'session expired' } }, 401),
        ),
    )
    await expect(apiClient.get('/items')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not invoke the 401 handler when skipAuthRedirect is set (e.g. the login call itself)', async () => {
    const handler = vi.fn()
    onUnauthorized(handler)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ data: null, error: { code: 'AUTH_INVALID', message: 'bad credentials' } }, 401),
        ),
    )
    await expect(
      apiClient.post('/auth/login', { username: 'x', password: 'y' }, { skipAuthRedirect: true }),
    ).rejects.toBeInstanceOf(ApiError)
    expect(handler).not.toHaveBeenCalled()
  })

  it('sends the CSRF header on mutating requests when a csrf cookie is present', async () => {
    document.cookie = 'csrf_token=abc123; path=/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: null, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    await apiClient.post('/items', { foo: 'bar' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Headers
    expect(headers.get('X-CSRF-Token')).toBe('abc123')
  })

  it('does not send a CSRF header on safe GET requests', async () => {
    document.cookie = 'csrf_token=abc123; path=/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: null, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    await apiClient.get('/items')

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Headers
    expect(headers.get('X-CSRF-Token')).toBeNull()
  })
})

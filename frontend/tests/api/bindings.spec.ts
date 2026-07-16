import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createBinding,
  deleteBinding,
  listMyBindings,
  startLineBinding,
  startTelegramBinding,
} from '@/api/bindings'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('bindings api (mocked backend, 03-API-SPEC.md §2 通知綁定)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listMyBindings GETs /me/bindings and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [{ id: 'b1', channel: 'line', address: 'U***', is_verified: true }], error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listMyBindings()

    expect(result).toHaveLength(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/me/bindings')
    expect(init.method).toBe('GET')
  })

  it('startLineBinding POSTs /me/bindings/line/start', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { code: '123456', expires_at: '2026-07-12T00:10:00+08:00' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await startLineBinding()

    expect(result.code).toBe('123456')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/me/bindings/line/start')
    expect(init.method).toBe('POST')
  })

  it('startTelegramBinding POSTs /me/bindings/telegram/start and returns a deep link', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: { code: '654321', expires_at: '2026-07-12T00:10:00+08:00', deep_link: 'https://t.me/bot?start=654321' },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await startTelegramBinding()

    expect(result.deep_link).toBe('https://t.me/bot?start=654321')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/me/bindings/telegram/start')
  })

  it('createBinding POSTs /me/bindings/{channel} with the address body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: 'b2', channel: 'email', address: 'a***@b.com', is_verified: false }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createBinding('email', { address: 'a@b.com' })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/me/bindings/email')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ address: 'a@b.com' })
  })

  it('deleteBinding DELETEs /me/bindings/{id}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteBinding('b1')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/me/bindings/b1')
    expect(init.method).toBe('DELETE')
  })
})

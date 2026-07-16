import { afterEach, describe, expect, it, vi } from 'vitest'
import { createInitialAdmin, getSetupStatus } from '@/api/setup'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('setup api (mocked backend, SETUP-WIZARD backend/app/api/v1/setup.py)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getSetupStatus GETs /setup/status and returns needs_setup', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { needs_setup: true }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getSetupStatus()

    expect(result).toEqual({ needs_setup: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/setup/status')
    expect(init.method).toBe('GET')
  })

  it('createInitialAdmin POSTs the payload to /setup', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { ok: true }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await createInitialAdmin({
      email: 'admin@example.com',
      display_name: 'Admin',
      password: 'Sup3rSecretAdmin!',
    })

    expect(result).toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/setup')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      email: 'admin@example.com',
      display_name: 'Admin',
      password: 'Sup3rSecretAdmin!',
    })
  })

  it('createInitialAdmin does not send an X-CSRF-Token header (bootstrap, no session yet)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { ok: true }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    // No csrf_token cookie present in this jsdom document -- mirrors a real
    // first visit where no session has ever been established.
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/'

    await createInitialAdmin({
      email: 'admin@example.com',
      display_name: 'Admin',
      password: 'Sup3rSecretAdmin!',
    })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(headers.has('X-CSRF-Token')).toBe(false)
  })

  it('createInitialAdmin surfaces SETUP_ALREADY_DONE as a 409 ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { data: null, error: { code: 'SETUP_ALREADY_DONE', message: 'already done' } },
        409,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      createInitialAdmin({
        email: 'admin@example.com',
        display_name: 'Admin',
        password: 'Sup3rSecretAdmin!',
      }),
    ).rejects.toMatchObject({ code: 'SETUP_ALREADY_DONE', status: 409 })
  })
})

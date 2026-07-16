import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('setupStatus (SETUP-WIZARD router guard state)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  beforeEach(() => {
    vi.resetModules()
  })

  it('needsSetup fetches GET /setup/status and caches the result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { needs_setup: true }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { needsSetup } = await import('@/router/setupStatus')

    expect(await needsSetup()).toBe(true)
    expect(await needsSetup()).toBe(true)
    // Only one network round-trip for both calls -- the second is served
    // from cache.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('needsSetup fails open (treats a network error as "no setup needed")', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network error'))
    vi.stubGlobal('fetch', fetchMock)

    const { needsSetup } = await import('@/router/setupStatus')

    expect(await needsSetup()).toBe(false)
  })

  it('markSetupComplete short-circuits the cache without another fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { needs_setup: true }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { needsSetup, markSetupComplete } = await import('@/router/setupStatus')

    expect(await needsSetup()).toBe(true)
    markSetupComplete()
    expect(await needsSetup()).toBe(false)
    // markSetupComplete never triggers a fetch of its own.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('resetSetupStatusCache forces the next needsSetup() call to re-fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { needs_setup: false }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { needsSetup, resetSetupStatusCache } = await import('@/router/setupStatus')

    await needsSetup()
    resetSetupStatusCache()
    await needsSetup()

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  describe('resolveSetupRedirect (pure guard decision logic)', () => {
    it('sends an unsetup app to /setup from any other route', async () => {
      const { resolveSetupRedirect } = await import('@/router/setupStatus')
      expect(resolveSetupRedirect(true, 'dashboard')).toBe('setup')
      expect(resolveSetupRedirect(true, 'login')).toBe('setup')
      expect(resolveSetupRedirect(true, undefined)).toBe('setup')
    })

    it('does not redirect an unsetup app already headed to /setup (no loop)', async () => {
      const { resolveSetupRedirect } = await import('@/router/setupStatus')
      expect(resolveSetupRedirect(true, 'setup')).toBeNull()
    })

    it('bounces a completed setup away from /setup to /login', async () => {
      const { resolveSetupRedirect } = await import('@/router/setupStatus')
      expect(resolveSetupRedirect(false, 'setup')).toBe('login')
    })

    it('does not redirect a completed setup visiting any other route (no loop)', async () => {
      const { resolveSetupRedirect } = await import('@/router/setupStatus')
      expect(resolveSetupRedirect(false, 'dashboard')).toBeNull()
      expect(resolveSetupRedirect(false, 'login')).toBeNull()
    })
  })
})

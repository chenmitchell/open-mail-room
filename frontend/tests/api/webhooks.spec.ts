import { afterEach, describe, expect, it, vi } from 'vitest'
import { createWebhook, listWebhooks, testWebhook, updateWebhook } from '@/api/webhooks'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('webhooks api (mocked backend, 03-API-SPEC.md §2/§3 admin webhooks)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listWebhooks GETs /admin/webhooks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: [{ id: 'w1', name: 'ERP', url: 'https://example.com', events: ['item.received'], is_active: true, failure_count: 0 }],
        error: null,
        meta: { total: 1, page: 1, size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listWebhooks()

    expect(result.items).toHaveLength(1)
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/admin/webhooks')
  })

  it('createWebhook POSTs the payload and returns the one-time secret', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          id: 'w1',
          name: 'ERP',
          url: 'https://example.com',
          events: ['item.received'],
          is_active: true,
          failure_count: 0,
          secret: 'whsec_abc123',
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await createWebhook({ name: 'ERP', url: 'https://example.com', events: ['item.received'] })

    expect(result.secret).toBe('whsec_abc123')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/webhooks')
    expect(init.method).toBe('POST')
  })

  it('updateWebhook PATCHes /admin/webhooks/{id}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: 'w1', name: 'ERP', url: 'https://example.com', events: [], is_active: false, failure_count: 0 }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateWebhook('w1', { is_active: false })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/webhooks/w1')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ is_active: false })
  })

  it('testWebhook POSTs /admin/webhooks/{id}/test and returns the result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { success: true, status_code: 200, sent_at: '2026-07-12T00:00:00+08:00' }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await testWebhook('w1')

    expect(result).toEqual({ success: true, status_code: 200, sent_at: '2026-07-12T00:00:00+08:00' })
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/admin/webhooks/w1/test')
  })
})

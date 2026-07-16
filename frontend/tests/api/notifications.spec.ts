import { afterEach, describe, expect, it, vi } from 'vitest'
import { listNotifications } from '@/api/notifications'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('notifications api (mocked backend, ASSUMPTION GET /notifications — see src/api/notifications.ts)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listNotifications filters by status=dead and unwraps { data, meta }', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: [
          {
            id: 'n1',
            mail_item_id: 'i1',
            employee_id: 'e1',
            channel: 'line',
            template: 'received',
            status: 'dead',
            retries: 5,
          },
        ],
        error: null,
        meta: { total: 1, page: 1, size: 100 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listNotifications({ status: 'dead', size: 100 })

    expect(result.items).toHaveLength(1)
    expect(result.items[0].status).toBe('dead')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toContain('/api/v1/notifications?')
    expect(url).toContain('status=dead')
    expect(url).toContain('size=100')
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAiModels, getAiStatus, updateAiSettings } from '@/api/ai'
import { ApiError } from '@/api/client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// task brief M9-FE 「AI 設定」頁 — 03-API-SPEC.md admin/ai:
// GET /admin/ai/status, GET /admin/ai/models, PUT /admin/ai/settings.
describe('ai api (mocked backend)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getAiStatus GETs /admin/ai/status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          env_key_present: true,
          provider: 'gemini',
          effective_model: 'gemini-1.5-pro',
          daily_request_limit: 10000,
          used_today: 42,
          has_db_config: true,
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getAiStatus()

    expect(result.env_key_present).toBe(true)
    expect(result.used_today).toBe(42)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/ai/status')
    expect(init.method).toBe('GET')
  })

  it('getAiModels GETs /admin/ai/models and returns the model list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { models: ['gemini-1.5-pro', 'gemini-1.5-flash'] }, error: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getAiModels()

    expect(result.models).toEqual(['gemini-1.5-pro', 'gemini-1.5-flash'])
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/admin/ai/models')
  })

  it('getAiModels throws ApiError(AI_NO_KEY) when no env key is configured', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: null, error: { code: 'AI_NO_KEY', message: 'no key' } }, 400),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getAiModels()).rejects.toMatchObject({ code: 'AI_NO_KEY' })
  })

  it('getAiModels throws ApiError(AI_MODELS_UNAVAILABLE) when ListModels fails upstream', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { data: null, error: { code: 'AI_MODELS_UNAVAILABLE', message: 'upstream timeout' } },
        400,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    try {
      await getAiModels()
      expect.unreachable()
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).code).toBe('AI_MODELS_UNAVAILABLE')
      expect((err as ApiError).message).toBe('upstream timeout')
    }
  })

  it('updateAiSettings PUTs /admin/ai/settings with the payload and returns the new status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          env_key_present: true,
          provider: 'gemini',
          effective_model: 'gemini-1.5-flash',
          daily_request_limit: 500,
          used_today: 0,
          has_db_config: true,
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await updateAiSettings({ model: 'gemini-1.5-flash', daily_request_limit: 500 })

    expect(result.effective_model).toBe('gemini-1.5-flash')
    expect(result.daily_request_limit).toBe(500)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/ai/settings')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({ model: 'gemini-1.5-flash', daily_request_limit: 500 })
  })

  it('updateAiSettings sends model: null to clear the override back to auto-detect', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          env_key_present: true,
          provider: 'gemini',
          effective_model: '',
          daily_request_limit: 10000,
          used_today: 0,
          has_db_config: true,
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateAiSettings({ model: null, daily_request_limit: 10000 })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ model: null, daily_request_limit: 10000 })
  })
})

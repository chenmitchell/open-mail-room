import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // M4-02 bug fix regression test: backend/app/api/v1/auth.py `LoginRequest`
  // is `{ email, password }` — a prior version of this store sent
  // `{ username, password }` and every login attempt 422'd. This pins the
  // exact request body contract so it can't silently regress again.
  it('sends { email, password } as the POST /auth/login request body', async () => {
    const user = {
      id: '1',
      display_name: '王小明',
      email: 'counter01@example.com',
      role: 'counter',
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: user, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useAuthStore()
    await store.login('counter01@example.com', 'password')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(requestInit.body as string)).toEqual({
      email: 'counter01@example.com',
      password: 'password',
    })
  })

  it('login stores the returned user (display_name/pickup_code/department) and flips isAuthenticated on success', async () => {
    const user = {
      id: '1',
      display_name: '王小明',
      email: 'counter01@example.com',
      role: 'counter',
      department: '總務部',
      pickup_code: 'AB12CD34',
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: user, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useAuthStore()
    await store.login('counter01@example.com', 'password')

    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.display_name).toBe('王小明')
    expect(store.user?.department).toBe('總務部')
    expect(store.user?.pickup_code).toBe('AB12CD34')
    expect(store.status).toBe('ready')
  })

  it('login surfaces the backend error message and leaves the store unauthenticated', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ data: null, error: { code: 'AUTH_INVALID', message: '帳號或密碼錯誤' } }, 401),
      )
    vi.stubGlobal('fetch', fetchMock)

    const store = useAuthStore()
    await expect(store.login('counter01@example.com', 'wrong')).rejects.toThrow('帳號或密碼錯誤')

    expect(store.isAuthenticated).toBe(false)
    expect(store.user).toBeNull()
    expect(store.error).toBe('帳號或密碼錯誤')
  })

  it('logout clears the user even if the network call fails', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network down'))
    vi.stubGlobal('fetch', fetchMock)

    const store = useAuthStore()
    store.user = { id: '1', display_name: 'X', email: 'x@y.com', role: 'counter' }

    await expect(store.logout()).rejects.toThrow()
    expect(store.user).toBeNull()
  })
})

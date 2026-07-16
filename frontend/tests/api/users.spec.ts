import { afterEach, describe, expect, it, vi } from 'vitest'
import { changeMyPassword, createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('users api (mocked backend, M7-FE admin 使用者管理 contract)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('listUsers GETs /admin/users with the filter query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: [
          {
            id: 'u1',
            email: 'a@b.com',
            display_name: '王小明',
            role: 'counter',
            is_active: true,
            last_login_at: null,
            employee_id: null,
            employee_name: null,
            created_at: '2026-07-01T00:00:00Z',
            updated_at: '2026-07-01T00:00:00Z',
          },
        ],
        error: null,
        meta: { total: 1, page: 1, size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listUsers({ q: '小明', role: 'counter', is_active: true, page: 1, size: 20 })

    expect(result.items).toHaveLength(1)
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/admin/users?q=%E5%B0%8F%E6%98%8E&role=counter&is_active=true&page=1&size=20')
  })

  it('createUser POSTs /admin/users', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          id: 'u1',
          email: 'new@b.com',
          display_name: 'New User',
          role: 'employee',
          is_active: true,
          created_at: '2026-07-01T00:00:00Z',
          updated_at: '2026-07-01T00:00:00Z',
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createUser({ email: 'new@b.com', display_name: 'New User', role: 'employee', password: 'longenoughpw' })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/users')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      email: 'new@b.com',
      display_name: 'New User',
      role: 'employee',
      password: 'longenoughpw',
    })
  })

  it('updateUser PATCHes /admin/users/{id}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          id: 'u1',
          email: 'a@b.com',
          display_name: 'A',
          role: 'admin',
          is_active: false,
          created_at: '2026-07-01T00:00:00Z',
          updated_at: '2026-07-01T00:00:00Z',
        },
        error: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateUser('u1', { is_active: false })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/users/u1')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ is_active: false })
  })

  it('resetUserPassword POSTs /admin/users/{id}/reset-password', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { ok: true }, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await resetUserPassword('u1', { new_password: 'brandnewpassword' })

    expect(result).toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/admin/users/u1/reset-password')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ new_password: 'brandnewpassword' })
  })

  it('changeMyPassword POSTs /me/password', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { ok: true }, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await changeMyPassword({ current_password: 'old-pass', new_password: 'brandnewpassword' })

    expect(result).toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/me/password')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ current_password: 'old-pass', new_password: 'brandnewpassword' })
  })
})

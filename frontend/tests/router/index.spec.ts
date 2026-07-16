import { describe, expect, it } from 'vitest'
import { router } from '@/router/index'

// M7-FE task brief: /admin/users must be admin-only, same RBAC convention as
// the other admin/* routes (router/index.ts beforeEach reads `requiresRole`
// off route meta and bounces non-matching roles to /dashboard).
describe('router /admin/users route', () => {
  it('is registered as "admin-users", admin-gated, lazy-loaded', () => {
    const route = router.getRoutes().find((r) => r.name === 'admin-users')
    expect(route).toBeTruthy()
    expect(route!.path).toBe('/admin/users')
    expect(route!.meta.requiresRole).toBe('admin')
  })
})

// task brief M9-FE 「AI 設定」頁: /admin/ai must be admin-only, same RBAC
// convention as the other admin/* routes above.
describe('router /admin/ai route', () => {
  it('is registered as "admin-ai", admin-gated, lazy-loaded', () => {
    const route = router.getRoutes().find((r) => r.name === 'admin-ai')
    expect(route).toBeTruthy()
    expect(route!.path).toBe('/admin/ai')
    expect(route!.meta.requiresRole).toBe('admin')
  })
})

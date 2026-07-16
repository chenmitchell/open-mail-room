import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import AppShell from '@/pages/AppShell.vue'
import type { UserRole } from '@/types/api'

// M6-HELP: (1) every authenticated role gets a "使用說明" nav entry linking
// to /help, and (2) a role badge in the nav tells the user which of the
// four RBAC roles their account has.
function mountShell(role: UserRole) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role }

  const router = createRouter({
    history: createWebHistory(),
    routes: [{ path: '/', name: 'dashboard', component: { template: '<div />' } }],
  })
  router.push('/')

  return mount(AppShell, { global: { plugins: [i18n, pinia, router] } })
}

describe('AppShell', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it.each<UserRole>(['admin', 'counter', 'employee', 'viewer'])(
    'shows a "使用說明" nav link to /help for role=%s',
    async (role) => {
      const wrapper = mountShell(role)
      await flushPromises()

      const helpLink = wrapper.findAll('a').find((a) => a.text().includes('使用說明'))
      expect(helpLink).toBeTruthy()
      expect(helpLink!.attributes('href')).toBe('/help')
    },
  )

  it.each<[UserRole, string]>([
    ['admin', '管理員'],
    ['counter', '櫃台'],
    ['employee', '員工'],
    ['viewer', '唯讀'],
  ])('shows a role badge reading "%s" -> "%s"', async (role, expectedLabel) => {
    const wrapper = mountShell(role)
    await flushPromises()
    expect(wrapper.text()).toContain(expectedLabel)
  })

  // M7-FE task brief: 「使用者管理」nav entry is admin-only, mirroring the
  // router's `requiresRole: 'admin'` guard on /admin/users.
  it('shows a "使用者管理" nav link to /admin/users for admin only', async () => {
    const adminWrapper = mountShell('admin')
    await flushPromises()
    const adminLink = adminWrapper.findAll('a').find((a) => a.text().includes('使用者管理'))
    expect(adminLink).toBeTruthy()
    expect(adminLink!.attributes('href')).toBe('/admin/users')

    for (const role of ['counter', 'employee', 'viewer'] as UserRole[]) {
      const wrapper = mountShell(role)
      await flushPromises()
      const link = wrapper.findAll('a').find((a) => a.text().includes('使用者管理'))
      expect(link).toBeFalsy()
    }
  })

  // task brief M9-FE 「AI 設定」頁 nav entry is admin-only, mirroring the
  // router's `requiresRole: 'admin'` guard on /admin/ai.
  it('shows an "AI 設定" nav link to /admin/ai for admin only', async () => {
    const adminWrapper = mountShell('admin')
    await flushPromises()
    const adminLink = adminWrapper.findAll('a').find((a) => a.text().includes('AI 設定'))
    expect(adminLink).toBeTruthy()
    expect(adminLink!.attributes('href')).toBe('/admin/ai')

    for (const role of ['counter', 'employee', 'viewer'] as UserRole[]) {
      const wrapper = mountShell(role)
      await flushPromises()
      const link = wrapper.findAll('a').find((a) => a.text().includes('AI 設定'))
      expect(link).toBeFalsy()
    }
  })

  // M7-FE task brief: self-service 修改密碼 is available to every
  // authenticated role, unlike the admin-only 使用者管理 link above.
  it.each<UserRole>(['admin', 'counter', 'employee', 'viewer'])(
    'shows a "修改密碼" button that opens the change-password dialog for role=%s',
    async (role) => {
      const wrapper = mountShell(role)
      await flushPromises()

      const button = wrapper.findAll('button').find((b) => b.text() === '修改密碼')
      expect(button).toBeTruthy()

      await button!.trigger('click')
      await flushPromises()

      const body = new DOMWrapper(document.body)
      expect(body.text()).toContain('修改密碼')
      expect(body.find('input[type="password"]').exists()).toBe(true)
    },
  )
})

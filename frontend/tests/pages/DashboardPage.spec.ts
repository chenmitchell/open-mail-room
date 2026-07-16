import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'

// Bug fix regression test: 首頁「拍照登記」/「批次上傳」used to be hardcoded
// `disabled` with a "coming in M2" tooltip -- stale once the M2 pages
// (PhotoRegisterPage / BatchUploadPage, routes `inbound-photo` /
// `inbound-batch` in src/router/index.ts) actually shipped. This pins that
// both buttons are enabled and navigate to the right route on click.
vi.mock('@/api/items', () => ({ listItems: vi.fn() }))
import { listItems } from '@/api/items'
import DashboardPage from '@/pages/DashboardPage.vue'

function mountDashboard() {
  vi.mocked(listItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'counter' }

  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: DashboardPage },
      { path: '/register/photo', name: 'inbound-photo', component: { template: '<div />' } },
      { path: '/register/batch', name: 'inbound-batch', component: { template: '<div />' } },
      { path: '/pickup', name: 'pickup', component: { template: '<div />' } },
    ],
  })
  return { router, pinia }
}

describe('DashboardPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the photo-register and batch-upload buttons as enabled (not the stale M2 placeholder)', async () => {
    const { router, pinia } = mountDashboard()
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const photoButton = buttons.find((b) => b.text().includes('拍照登記'))
    const batchButton = buttons.find((b) => b.text().includes('批次上傳'))

    expect(photoButton).toBeDefined()
    expect(batchButton).toBeDefined()
    expect(photoButton!.attributes('disabled')).toBeUndefined()
    expect(batchButton!.attributes('disabled')).toBeUndefined()
    expect(photoButton!.attributes('title')).toBeUndefined()
    expect(batchButton!.attributes('title')).toBeUndefined()
  })

  it('navigates to the inbound-photo route when "拍照登記" is clicked', async () => {
    const { router, pinia } = mountDashboard()
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const pushSpy = vi.spyOn(router, 'push')
    const photoButton = wrapper.findAll('button').find((b) => b.text().includes('拍照登記'))
    await photoButton!.trigger('click')

    expect(pushSpy).toHaveBeenCalledWith({ name: 'inbound-photo' })
  })

  it('navigates to the inbound-batch route when "批次上傳" is clicked', async () => {
    const { router, pinia } = mountDashboard()
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const pushSpy = vi.spyOn(router, 'push')
    const batchButton = wrapper.findAll('button').find((b) => b.text().includes('批次上傳'))
    await batchButton!.trigger('click')

    expect(pushSpy).toHaveBeenCalledWith({ name: 'inbound-batch' })
  })
})

// M6-HELP 角色化強化: `employee` doesn't do intake/pickup (01 §1 RBAC), so
// the dashboard collapses to a short panel pointing at 我的郵件/通知設定/
// 使用說明 instead of the counter/admin big-button + stats layout.
describe('DashboardPage role-based content', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('employee: shows the simplified panel (我的郵件/通知設定/使用說明), not the receiving-desk buttons or stats', async () => {
    vi.mocked(listItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u2', display_name: '林小美', email: 'lin@b.com', role: 'employee' }

    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', name: 'dashboard', component: DashboardPage },
        { path: '/my-mail', name: 'my-mail', component: { template: '<div />' } },
        { path: '/notifications/settings', name: 'notification-settings', component: { template: '<div />' } },
        { path: '/help', name: 'help', component: { template: '<div />' } },
      ],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const buttons = wrapper.findAll('button').map((b) => b.text())
    expect(buttons).toContain('我的郵件')
    expect(buttons).toContain('通知設定')
    expect(buttons).toContain('使用說明')
    expect(buttons).not.toContain('拍照登記')
    expect(buttons).not.toContain('批次上傳')
    expect(buttons).not.toContain('領取核銷')
    // Stats cards are receiving-desk data; the employee panel doesn't fetch them.
    expect(listItems).not.toHaveBeenCalled()
  })

  it('employee: clicking "我的郵件" navigates to the my-mail route', async () => {
    vi.mocked(listItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u2', display_name: '林小美', email: 'lin@b.com', role: 'employee' }

    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', name: 'dashboard', component: DashboardPage },
        { path: '/my-mail', name: 'my-mail', component: { template: '<div />' } },
        { path: '/notifications/settings', name: 'notification-settings', component: { template: '<div />' } },
        { path: '/help', name: 'help', component: { template: '<div />' } },
      ],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const pushSpy = vi.spyOn(router, 'push')
    const myMailButton = wrapper.findAll('button').find((b) => b.text() === '我的郵件')
    await myMailButton!.trigger('click')
    expect(pushSpy).toHaveBeenCalledWith({ name: 'my-mail' })
  })

  it('viewer: shows the read-only panel (查詢/報表), not the receiving-desk buttons', async () => {
    vi.mocked(listItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u3', display_name: '查詢者', email: 'v@b.com', role: 'viewer' }

    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', name: 'dashboard', component: DashboardPage },
        { path: '/search', name: 'search', component: { template: '<div />' } },
        { path: '/reports', name: 'reports', component: { template: '<div />' } },
      ],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    const buttons = wrapper.findAll('button').map((b) => b.text())
    expect(buttons).toContain('查詢')
    expect(buttons).toContain('報表')
    expect(buttons).not.toContain('拍照登記')
    expect(buttons).not.toContain('領取核銷')
    expect(listItems).not.toHaveBeenCalled()
  })

  it('counter: still shows the full receiving-desk dashboard (regression -- role branching must not break the existing role)', async () => {
    vi.mocked(listItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'counter' }

    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', name: 'dashboard', component: DashboardPage },
        { path: '/register/photo', name: 'inbound-photo', component: { template: '<div />' } },
        { path: '/register/batch', name: 'inbound-batch', component: { template: '<div />' } },
        { path: '/pickup', name: 'pickup', component: { template: '<div />' } },
      ],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(DashboardPage, { global: { plugins: [i18n, pinia, router] } })
    await flushPromises()

    expect(listItems).toHaveBeenCalled()
    const buttons = wrapper.findAll('button').map((b) => b.text())
    expect(buttons).toContain('拍照登記')
    expect(buttons).toContain('批次上傳')
    expect(buttons).toContain('領取核銷')
  })
})

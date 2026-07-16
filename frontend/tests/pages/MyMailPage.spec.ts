import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'

// 06-UI-UX.md §1 「我的郵件」(employee): 待領清單(取件碼大字)、歷史.
vi.mock('@/api/myItems', () => ({ listMyItems: vi.fn() }))
import { listMyItems } from '@/api/myItems'
import MyMailPage from '@/pages/employee/MyMailPage.vue'
import type { MailItem } from '@/types/api'

function item(overrides: Partial<MailItem>): MailItem {
  return {
    id: overrides.id ?? 'i1',
    item_no: overrides.item_no ?? 'IN-20260712-0001',
    mail_type: 'parcel',
    recipient_name_raw: '王小明',
    received_at: '2026-07-12T09:00:00+08:00',
    status: 'notified',
    is_confidential: false,
    is_cod: false,
    refrigeration: 'none',
    remind_count: 0,
    ...overrides,
  }
}

describe('MyMailPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the employee pickup code in large text', async () => {
    vi.mocked(listMyItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'employee', pickup_code: 'AB12CD34' }
    const wrapper = mount(MyMailPage, { global: { plugins: [i18n, pinia] } })
    await flushPromises()

    expect(wrapper.find('.my-mail-page__code-value').text()).toBe('AB12CD34')
  })

  it('shows a fallback message when the employee has no linked pickup code', async () => {
    vi.mocked(listMyItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: 'X', email: 'x@y.com', role: 'admin' }
    const wrapper = mount(MyMailPage, { global: { plugins: [i18n, pinia] } })
    await flushPromises()

    expect(wrapper.find('.my-mail-page__code-value').exists()).toBe(false)
    expect(wrapper.text()).toContain('尚未取得取件碼')
  })

  it('splits items into pending (received/notified/unclaimed) and history sections', async () => {
    vi.mocked(listMyItems).mockResolvedValue({
      items: [
        item({ id: 'p1', status: 'notified' }),
        item({ id: 'p2', status: 'received' }),
        item({ id: 'h1', status: 'picked_up', picked_up_at: '2026-07-10T10:00:00+08:00' }),
        item({ id: 'h2', status: 'returned' }),
      ],
      meta: { total: 4, page: 1, size: 20 },
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'employee', pickup_code: 'AB12CD34' }
    const wrapper = mount(MyMailPage, { global: { plugins: [i18n, pinia] } })
    await flushPromises()

    const sections = wrapper.findAll('.my-mail-page__section')
    expect(sections).toHaveLength(2)
    const pendingItems = sections[0].findAll('.my-mail-page__item')
    const historyItems = sections[1].findAll('.my-mail-page__item')
    expect(pendingItems).toHaveLength(2)
    expect(historyItems).toHaveLength(2)
  })

  it('shows the empty state when there is no mail at all', async () => {
    vi.mocked(listMyItems).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'employee', pickup_code: 'AB12CD34' }
    const wrapper = mount(MyMailPage, { global: { plugins: [i18n, pinia] } })
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有待領取的郵件')
    expect(wrapper.text()).toContain('目前沒有歷史紀錄')
  })

  it('shows a "load more" button when more items exist beyond the current page', async () => {
    vi.mocked(listMyItems).mockResolvedValue({
      items: [item({ id: 'p1' })],
      meta: { total: 5, page: 1, size: 20 },
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'employee', pickup_code: 'AB12CD34' }
    const wrapper = mount(MyMailPage, { global: { plugins: [i18n, pinia] } })
    await flushPromises()

    const loadMoreButtons = wrapper.findAll('button').filter((b) => b.text().includes('載入更多'))
    expect(loadMoreButtons).toHaveLength(1)
  })
})

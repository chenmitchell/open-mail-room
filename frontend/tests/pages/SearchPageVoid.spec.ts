import { afterEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '@/i18n'

vi.mock('@/api/items', () => ({ listItems: vi.fn(), voidItem: vi.fn() }))
vi.mock('@/api/carriers', () => ({ listCarriers: vi.fn() }))
vi.mock('@/api/departments', () => ({ listDepartments: vi.fn() }))

import { listItems, voidItem } from '@/api/items'
import { listCarriers } from '@/api/carriers'
import { listDepartments } from '@/api/departments'
import { useAuthStore } from '@/stores/auth'
import SearchPage from '@/pages/search/SearchPage.vue'
import type { MailItem, MailItemStatus, UserRole } from '@/types/api'

function item(overrides: Partial<MailItem> = {}): MailItem {
  return {
    id: 'i1',
    item_no: 'IN-20260716-0001',
    direction: 'inbound',
    mail_type: 'parcel',
    recipient_name_raw: '王小明',
    received_at: '2026-07-16T01:00:00+00:00',
    status: 'received' as MailItemStatus,
    is_confidential: false,
    is_cod: false,
    refrigeration: 'none',
    remind_count: 0,
    created_at: '2026-07-16T01:00:00+00:00',
    updated_at: '2026-07-16T01:00:00+00:00',
    ...overrides,
  } as MailItem
}

async function mountPage(role: UserRole = 'counter', overrides: Partial<MailItem> = {}) {
  setActivePinia(createPinia())
  const auth = useAuthStore()
  auth.user = { id: 'u1', display_name: '櫃台', email: 'a@b.com', role }
  vi.mocked(listItems).mockResolvedValue({ items: [item(overrides)], meta: { total: 1, page: 1, size: 20 } })
  vi.mocked(listCarriers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  vi.mocked(listDepartments).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  const wrapper = mount(SearchPage, { global: { plugins: [i18n] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

/** 打開明細抽屜 */
async function openDetail(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('.search-page__detail-btn').trigger('click')
  await flushPromises()
}

function body() {
  return new DOMWrapper(document.body)
}

describe('SearchPage — 作廢登記', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('櫃台在明細裡看得到作廢按鈕', async () => {
    const wrapper = await mountPage('counter')
    await openDetail(wrapper)
    expect(body().text()).toContain('作廢這筆登記')
    wrapper.unmount()
  })

  it('唯讀角色看不到作廢按鈕 —— 作廢是更正登記,不是查詢', async () => {
    const wrapper = await mountPage('viewer')
    await openDetail(wrapper)
    expect(body().text()).not.toContain('作廢這筆登記')
    wrapper.unmount()
  })

  it('已領取的件不給作廢 —— 那個簽名記錄的是真的發生過的事', async () => {
    const wrapper = await mountPage('counter', { status: 'picked_up' as MailItemStatus })
    await openDetail(wrapper)
    expect(body().text()).not.toContain('作廢這筆登記')
    wrapper.unmount()
  })

  it('沒填理由時確定鍵是停用的', async () => {
    const wrapper = await mountPage('counter')
    await openDetail(wrapper)
    await body().find('.search-page__detail-actions button').trigger('click')
    await flushPromises()

    const confirm = body()
      .findAll('.search-page__void-buttons button')
      .find((b) => b.text().includes('確定作廢'))
    expect(confirm?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('填了理由後送出,理由會傳給後端', async () => {
    vi.mocked(voidItem).mockResolvedValue(item({ status: 'voided' as MailItemStatus }))
    const wrapper = await mountPage('counter')
    await openDetail(wrapper)
    await body().find('.search-page__detail-actions button').trigger('click')
    await flushPromises()

    const input = body().find('.app-dialog input[type="text"]')
    await input.setValue('重複登記')
    const confirm = body()
      .findAll('.search-page__void-buttons button')
      .find((b) => b.text().includes('確定作廢'))
    await confirm!.trigger('click')
    await flushPromises()

    expect(voidItem).toHaveBeenCalledWith('i1', '重複登記')
    wrapper.unmount()
  })
})

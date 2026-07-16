import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

// task brief 「通知失敗清單」(counter/admin): dead 通知列表 + 重發按鈕.
vi.mock('@/api/notifications', () => ({ listNotifications: vi.fn() }))
vi.mock('@/api/items', () => ({ notifyItem: vi.fn() }))
import { listNotifications } from '@/api/notifications'
import { notifyItem } from '@/api/items'
import NotificationFailuresPage from '@/pages/notifications/NotificationFailuresPage.vue'
import type { NotificationRecord } from '@/types/api'

function record(overrides: Partial<NotificationRecord> = {}): NotificationRecord {
  return {
    id: 'n1',
    mail_item_id: 'item-1',
    item_no: 'IN-20260712-0001',
    recipient_name: '王小明',
    employee_id: 'e1',
    channel: 'line',
    template: 'received',
    status: 'dead',
    error: 'LINE_QUOTA_EXCEEDED',
    retries: 5,
    ...overrides,
  }
}

function mountPage() {
  return mount(NotificationFailuresPage, { global: { plugins: [i18n] } })
}

describe('NotificationFailuresPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches only dead notifications and shows the empty state when there are none', async () => {
    vi.mocked(listNotifications).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 100 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(listNotifications).toHaveBeenCalledWith({ status: 'dead', size: 100 })
    expect(wrapper.text()).toContain('目前沒有失敗的通知')
  })

  it('renders a row per dead notification with item/recipient/channel/error/retries', async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      items: [record()],
      meta: { total: 1, page: 1, size: 100 },
    })
    const wrapper = mountPage()
    await flushPromises()

    const row = wrapper.find('tbody tr')
    expect(row.text()).toContain('IN-20260712-0001')
    expect(row.text()).toContain('王小明')
    expect(row.text()).toContain('LINE_QUOTA_EXCEEDED')
    expect(row.text()).toContain('5')
  })

  it('resending calls POST /items/{id}/notify with the mail_item_id and shows a success message', async () => {
    vi.mocked(listNotifications).mockResolvedValue({ items: [record()], meta: { total: 1, page: 1, size: 100 } })
    vi.mocked(notifyItem).mockResolvedValue({
      id: 'item-1',
      item_no: 'IN-20260712-0001',
      mail_type: 'parcel',
      recipient_name_raw: '王小明',
      received_at: '2026-07-12T09:00:00+08:00',
      status: 'notified',
      is_confidential: false,
      is_cod: false,
      refrigeration: 'none',
      remind_count: 0,
    })

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('tbody tr button').trigger('click')
    await flushPromises()

    expect(notifyItem).toHaveBeenCalledWith('item-1')
    expect(wrapper.text()).toContain('已重新發送通知')
    // The dead-list row stays visible with its success message rather than
    // being wiped by an immediate reload -- see the component's resend()
    // comment for why.
    expect(listNotifications).toHaveBeenCalledTimes(1)
  })

  it('shows a resend failure message and keeps the row in place', async () => {
    vi.mocked(listNotifications).mockResolvedValue({ items: [record()], meta: { total: 1, page: 1, size: 100 } })
    const { ApiError } = await import('@/api/client')
    vi.mocked(notifyItem).mockRejectedValue(new ApiError('OCR_PROVIDER_DOWN', '通知服務暫時無法使用', 502))

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('tbody tr button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('通知服務暫時無法使用')
  })
})

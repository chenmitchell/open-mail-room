import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { DOMWrapper } from '@vue/test-utils'
import { i18n } from '@/i18n'

// task brief 「admin webhooks 頁」: 列表/新增/停用/test(顯示結果).
vi.mock('@/api/webhooks', () => ({
  listWebhooks: vi.fn(),
  createWebhook: vi.fn(),
  updateWebhook: vi.fn(),
  testWebhook: vi.fn(),
}))
import { createWebhook, listWebhooks, testWebhook, updateWebhook } from '@/api/webhooks'
import WebhooksAdminPage from '@/pages/admin/WebhooksAdminPage.vue'
import type { WebhookEndpoint } from '@/types/api'

function webhook(overrides: Partial<WebhookEndpoint> = {}): WebhookEndpoint {
  return {
    id: 'w1',
    name: 'ERP Sync',
    url: 'https://erp.example.com/hooks/mailroom',
    events: ['item.received'],
    is_active: true,
    failure_count: 0,
    ...overrides,
  }
}

function mountPage() {
  return mount(WebhooksAdminPage, { global: { plugins: [i18n] }, attachTo: document.body })
}

describe('WebhooksAdminPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('lists existing webhooks', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [webhook()], meta: { total: 1, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('ERP Sync')
    expect(wrapper.text()).toContain('https://erp.example.com/hooks/mailroom')
    wrapper.unmount()
  })

  it('shows the empty state when there are no webhooks', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('尚未設定任何 Webhook')
    wrapper.unmount()
  })

  it('validates the create form before submitting (name/url/events required)', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入名稱')
    expect(wrapper.text()).toContain('請輸入 URL')
    expect(wrapper.text()).toContain('請至少選擇一個訂閱事件')
    expect(createWebhook).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('creates a webhook and reveals the one-time secret', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    vi.mocked(createWebhook).mockResolvedValue({ ...webhook(), secret: 'whsec_topsecret' })

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('input[type="text"]').setValue('ERP Sync')
    await wrapper.find('input[type="url"]').setValue('https://erp.example.com/hooks/mailroom')
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createWebhook).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'ERP Sync', url: 'https://erp.example.com/hooks/mailroom' }),
    )

    const body = new DOMWrapper(document.body)
    expect(body.text()).toContain('Webhook 已建立')
    expect(body.text()).toContain('whsec_topsecret')
    wrapper.unmount()
  })

  it('toggles a webhook active/inactive via PATCH', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [webhook({ is_active: true })], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(updateWebhook).mockResolvedValue(webhook({ is_active: false }))

    const wrapper = mountPage()
    await flushPromises()

    const deactivateButton = wrapper.findAll('button').find((b) => b.text() === '停用')
    expect(deactivateButton).toBeTruthy()
    await deactivateButton?.trigger('click')
    await flushPromises()

    expect(updateWebhook).toHaveBeenCalledWith('w1', { is_active: false })
    wrapper.unmount()
  })

  it('runs a test and displays a success result with the HTTP status', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [webhook()], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(testWebhook).mockResolvedValue({ success: true, status_code: 200, sent_at: '2026-07-12T00:00:00+08:00' })

    const wrapper = mountPage()
    await flushPromises()

    const testButton = wrapper.findAll('button').find((b) => b.text() === '測試')
    await testButton?.trigger('click')
    await flushPromises()

    expect(testWebhook).toHaveBeenCalledWith('w1')
    expect(wrapper.text()).toContain('測試成功')
    expect(wrapper.text()).toContain('200')
    wrapper.unmount()
  })

  it('runs a test and displays a failure result with the error message', async () => {
    vi.mocked(listWebhooks).mockResolvedValue({ items: [webhook()], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(testWebhook).mockResolvedValue({ success: false, message: 'connection refused', sent_at: '2026-07-12T00:00:00+08:00' })

    const wrapper = mountPage()
    await flushPromises()

    const testButton = wrapper.findAll('button').find((b) => b.text() === '測試')
    await testButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('測試失敗')
    expect(wrapper.text()).toContain('connection refused')
    wrapper.unmount()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

// 06-UI-UX.md §1 通知設定頁: 綁定清單、LINE/Telegram 精靈、直接綁定表單、解除
// 綁定確認.
vi.mock('@/api/bindings', () => ({
  listMyBindings: vi.fn(),
  deleteBinding: vi.fn(),
  startLineBinding: vi.fn(),
  startTelegramBinding: vi.fn(),
}))
import { deleteBinding, listMyBindings } from '@/api/bindings'
import NotificationSettingsPage from '@/pages/employee/NotificationSettingsPage.vue'
import type { NotificationBinding } from '@/types/api'

function mountPage() {
  return mount(NotificationSettingsPage, { global: { plugins: [i18n] } })
}

describe('NotificationSettingsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the empty state when no channels are bound', async () => {
    vi.mocked(listMyBindings).mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('尚未綁定任何通知通道')
  })

  it('renders each binding with its verified/unverified state (icon+colour+text, never colour alone)', async () => {
    const bindings: NotificationBinding[] = [
      { id: 'b1', channel: 'line', address: 'U***abcd', is_verified: true },
      { id: 'b2', channel: 'email', address: 'a***@b.com', is_verified: false },
    ]
    vi.mocked(listMyBindings).mockResolvedValue(bindings)
    const wrapper = mountPage()
    await flushPromises()

    const items = wrapper.findAll('.notification-settings-page__binding')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('LINE')
    expect(items[0].text()).toContain('已驗證')
    expect(items[1].text()).toContain('Email')
    expect(items[1].text()).toContain('待驗證')
  })

  it('renders one direct-binding form per direct channel (email/slack/discord/webhook)', async () => {
    vi.mocked(listMyBindings).mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    // One <form> per DirectBindingForm instance (email/slack/discord/webhook).
    expect(wrapper.findAll('form')).toHaveLength(4)
  })

  it('confirms before unbinding, then calls deleteBinding and refreshes the list', async () => {
    const bindings: NotificationBinding[] = [{ id: 'b1', channel: 'line', address: 'U***abcd', is_verified: true }]
    vi.mocked(listMyBindings).mockResolvedValueOnce(bindings).mockResolvedValueOnce([])
    vi.mocked(deleteBinding).mockResolvedValue(undefined)

    // AppDialog renders via <Teleport to="body">, so its footer button lives
    // outside `wrapper.element` in the real DOM once open — mount attached to
    // `document.body` and query through a DOMWrapper around it for that part.
    const wrapper = mount(NotificationSettingsPage, {
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.find('.notification-settings-page__unbind-btn').trigger('click')
    await flushPromises()

    // Confirmation dialog is shown before anything is deleted.
    expect(deleteBinding).not.toHaveBeenCalled()
    const body = new DOMWrapper(document.body)
    expect(body.text()).toContain('確認解除綁定')

    const dialogConfirmButton = body
      .findAll('.app-dialog__footer button')
      .find((b) => b.text() === '解除綁定')
    expect(dialogConfirmButton).toBeTruthy()
    await dialogConfirmButton?.trigger('click')
    await flushPromises()

    expect(deleteBinding).toHaveBeenCalledWith('b1')
    expect(listMyBindings).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })
})

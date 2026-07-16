import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

vi.mock('@/api/bindings', () => ({ createBinding: vi.fn() }))
import { createBinding } from '@/api/bindings'
import DirectBindingForm from '@/components/DirectBindingForm.vue'

// 05-NOTIFICATIONS.md §2 adapter table: email/slack/discord/webhook bind
// directly with an address, no code wizard.
describe('DirectBindingForm', () => {
  it('rejects an empty address', async () => {
    const wrapper = mount(DirectBindingForm, {
      global: { plugins: [i18n] },
      props: { channel: 'email' },
    })

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入地址')
    expect(createBinding).not.toHaveBeenCalled()
  })

  it('validates an email address for the email channel', async () => {
    const wrapper = mount(DirectBindingForm, {
      global: { plugins: [i18n] },
      props: { channel: 'email' },
    })

    await wrapper.find('input').setValue('not-an-email')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入有效的 Email 地址')
    expect(createBinding).not.toHaveBeenCalled()
  })

  it('validates an https:// URL for webhook/slack/discord channels', async () => {
    const wrapper = mount(DirectBindingForm, {
      global: { plugins: [i18n] },
      props: { channel: 'webhook' },
    })

    await wrapper.find('input').setValue('http://insecure.example.com')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入有效的網址')
    expect(createBinding).not.toHaveBeenCalled()
  })

  it('submits a valid address and emits "added" with the created binding', async () => {
    const binding = { id: 'b1', channel: 'email' as const, address: 'a***@b.com', is_verified: false }
    vi.mocked(createBinding).mockResolvedValue(binding)

    const wrapper = mount(DirectBindingForm, {
      global: { plugins: [i18n] },
      props: { channel: 'email' },
    })

    await wrapper.find('input').setValue('a@b.com')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createBinding).toHaveBeenCalledWith('email', { address: 'a@b.com' })
    expect(wrapper.emitted('added')?.[0]).toEqual([binding])
    // Field clears after a successful submit.
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
  })

  it('surfaces a backend error without clearing the field', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(createBinding).mockRejectedValue(new ApiError('VALIDATION_ERROR', '地址已被使用', 400))

    const wrapper = mount(DirectBindingForm, {
      global: { plugins: [i18n] },
      props: { channel: 'email' },
    })

    await wrapper.find('input').setValue('a@b.com')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('地址已被使用')
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('a@b.com')
  })
})

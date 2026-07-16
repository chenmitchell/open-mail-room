import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'
import BindingCodeWizard from '@/components/BindingCodeWizard.vue'
import type { NotificationBinding, TelegramBindingStartResult } from '@/types/api'

// 05-NOTIFICATIONS.md §3 綁定精靈狀態機 driven end-to-end through the
// component: idle -> starting -> waiting(code, aria-live) -> success/timeout.
// The pure polling logic itself is covered exhaustively in
// tests/notifications/pollBinding.spec.ts; this spec proves the component
// wires start/poll/emit correctly.
function mountWizard(overrides: Record<string, unknown> = {}) {
  return mount(BindingCodeWizard, {
    global: { plugins: [i18n] },
    props: {
      channel: 'line',
      existingBindings: [],
      startFn: vi.fn(),
      fetchBindings: vi.fn(),
      ...overrides,
    } as never,
  })
}

describe('BindingCodeWizard', () => {
  it('starts idle with a "綁定 LINE" button', () => {
    const wrapper = mountWizard()
    expect(wrapper.text()).toContain('綁定 LINE')
    expect(wrapper.find('.binding-code-wizard__code').exists()).toBe(false)
  })

  it('walks through start -> waiting(code, aria-live) -> success and emits "bound"', async () => {
    const startFn = vi.fn().mockResolvedValue({ code: '123456', expires_at: '2999-01-01T00:00:00Z' })
    const verifiedBinding: NotificationBinding = {
      id: 'new-1',
      channel: 'line',
      address: 'U***',
      is_verified: true,
    }
    // Resolves already-verified on the very first poll fetch -> the wizard
    // reaches "success" without any real waiting.
    const fetchBindings = vi.fn().mockResolvedValue([verifiedBinding])

    const wrapper = mountWizard({ startFn, fetchBindings })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(startFn).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('bound')).toBeTruthy()
    expect(wrapper.emitted('bound')?.[0]).toEqual([verifiedBinding])
    expect(wrapper.text()).toContain('綁定成功')
  })

  it('shows the code with aria-live="polite" while waiting', async () => {
    const startFn = vi.fn().mockResolvedValue({ code: '654321', expires_at: '2999-01-01T00:00:00Z' })
    // Never resolves to verified -> stays in "waiting" so we can inspect the
    // intermediate state (long enough for the assertion, not the full 10 min
    // poll -- the test doesn't await the returned promise from `start()`).
    let resolveFetch: (() => void) | undefined
    const fetchBindings = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = () => resolve([])
        }),
    )

    const wrapper = mountWizard({ startFn, fetchBindings })
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const codeEl = wrapper.find('.binding-code-wizard__code')
    expect(codeEl.exists()).toBe(true)
    expect(codeEl.attributes('aria-live')).toBe('polite')
    expect(codeEl.text()).toBe('654321')

    // Cleanup: let the pending fetch resolve so the test doesn't leak a
    // dangling unhandled poll loop into the next test.
    resolveFetch?.()
    await flushPromises()
  })

  it('shows a deep-link button for telegram using the start response', async () => {
    const startResult: TelegramBindingStartResult = {
      code: '111222',
      expires_at: '2999-01-01T00:00:00Z',
      deep_link: 'https://t.me/mybot?start=111222',
    }
    const startFn = vi.fn().mockResolvedValue(startResult)
    let resolveFetch: (() => void) | undefined
    const fetchBindings = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = () => resolve([])
        }),
    )

    const wrapper = mountWizard({ channel: 'telegram', startFn, fetchBindings })
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const link = wrapper.find('.binding-code-wizard__deep-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://t.me/mybot?start=111222')

    resolveFetch?.()
    await flushPromises()
  })

  it('shows an error state when starting fails', async () => {
    const startFn = vi.fn().mockRejectedValue(new Error('network down'))
    const wrapper = mountWizard({ startFn, fetchBindings: vi.fn() })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })
})

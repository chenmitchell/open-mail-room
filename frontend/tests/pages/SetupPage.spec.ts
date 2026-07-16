import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { i18n } from '@/i18n'

// SETUP-WIZARD first-run "create the initial administrator" form.
vi.mock('@/api/setup', () => ({
  getSetupStatus: vi.fn(),
  createInitialAdmin: vi.fn(),
}))

import { createInitialAdmin } from '@/api/setup'
import SetupPage from '@/pages/SetupPage.vue'

describe('SetupPage (SETUP-WIZARD first-run "create the initial administrator" form)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function mountPage() {
    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/setup', name: 'setup', component: SetupPage },
        { path: '/login', name: 'login', component: { template: '<div />' } },
      ],
    })
    router.push('/setup')
    await router.isReady()
    const wrapper = mount(SetupPage, { global: { plugins: [i18n, router] } })
    return { wrapper, router }
  }

  async function fillForm(
    wrapper: Awaited<ReturnType<typeof mountPage>>['wrapper'],
    overrides: Partial<{ email: string; displayName: string; password: string; confirm: string }> = {},
  ) {
    const inputs = wrapper.findAll('input')
    const [emailInput, nameInput, passwordInput, confirmInput] = inputs
    await emailInput.setValue(overrides.email ?? 'admin@example.com')
    await nameInput.setValue(overrides.displayName ?? 'Admin')
    await passwordInput.setValue(overrides.password ?? 'Sup3rSecretAdmin!')
    await confirmInput.setValue(overrides.confirm ?? overrides.password ?? 'Sup3rSecretAdmin!')
  }

  it('renders email, display name, password, and confirm-password fields', async () => {
    const { wrapper } = await mountPage()
    const inputs = wrapper.findAll('input')
    expect(inputs).toHaveLength(4)
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.findAll('input[type="password"]')).toHaveLength(2)
  })

  it('blocks submit and shows an error when the password is too short', async () => {
    const { wrapper } = await mountPage()

    await fillForm(wrapper, { password: 'short1', confirm: 'short1' })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createInitialAdmin).not.toHaveBeenCalled()
    expect(wrapper.text()).toMatch(/10/)
  })

  it('blocks submit and shows an error when the passwords do not match', async () => {
    const { wrapper } = await mountPage()

    await fillForm(wrapper, {
      password: 'Sup3rSecretAdmin!',
      confirm: 'DifferentSecretAdmin!',
    })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createInitialAdmin).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(wrapper.vm.$t('setup.errors.passwordMismatch'))
  })

  it('submits the trimmed payload and redirects to /login on success', async () => {
    vi.mocked(createInitialAdmin).mockResolvedValue({ ok: true })
    const { wrapper, router } = await mountPage()

    await fillForm(wrapper, {
      email: '  new-admin@example.com  ',
      displayName: '  First Admin  ',
      password: 'Sup3rSecretAdmin!',
      confirm: 'Sup3rSecretAdmin!',
    })
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createInitialAdmin).toHaveBeenCalledWith({
      email: 'new-admin@example.com',
      display_name: 'First Admin',
      password: 'Sup3rSecretAdmin!',
    })
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.setup).toBe('done')
  })
})

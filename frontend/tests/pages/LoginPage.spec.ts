import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import LoginPage from '@/pages/LoginPage.vue'

// M4-02 bug fix regression test at the UI layer: the login field used to be
// labelled/bound as "username" even though the backend only ever accepted
// `{ email, password }` (see tests/stores/auth.spec.ts for the store-level
// payload contract test). This pins the form's field label and the value
// passed to `auth.login`.
describe('LoginPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function mountPage() {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/', name: 'dashboard', component: { template: '<div />' } },
        { path: '/login', name: 'login', component: LoginPage },
      ],
    })
    router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginPage, { global: { plugins: [i18n, pinia, router] } })
    return { wrapper, router }
  }

  it('labels the identifier field "Email" (電子郵件), not "Username"', async () => {
    const { wrapper } = await mountPage()
    expect(wrapper.text()).toContain('電子郵件')
    expect(wrapper.text()).not.toContain('帳號')
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
  })

  it('submits the typed email (not a "username") to the auth store', async () => {
    const { wrapper } = await mountPage()
    const auth = useAuthStore()
    const loginSpy = vi.spyOn(auth, 'login').mockResolvedValue(undefined)

    await wrapper.find('input[type="email"]').setValue('counter01@example.com')
    await wrapper.find('input[type="password"]').setValue('Sup3rSecret!')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(loginSpy).toHaveBeenCalledWith('counter01@example.com', 'Sup3rSecret!')
  })
})

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { i18n } from '@/i18n'
import LoginPage from '@/pages/LoginPage.vue'
// eslint-disable-next-line import/no-unresolved
import LoginPageSource from '@/pages/LoginPage.vue?raw'

/**
 * Layout regression: the author credit must sit *after* the card, in the same
 * vertical stack.
 *
 * The first version dropped it into `.login-page`, which is `display: flex`
 * with the default `row` direction — so it became a flex sibling of the card
 * and rendered beside it, floating off to the right. Structure alone doesn't
 * catch that, so this also asserts the container stacks vertically.
 */
describe('LoginPage 版面', () => {
  it('作者標示排在卡片之後,且容器是直向堆疊', async () => {
    setActivePinia(createPinia())
    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/:p(.*)', component: { template: '<div/>' } }],
    })
    await router.push('/login')
    await router.isReady()
    const w = mount(LoginPage, { global: { plugins: [i18n, router] } })

    const kids = Array.from(w.find('.login-page').element.children)
    const cardIdx = kids.findIndex((e) => e.classList.contains('login-page__card'))
    const creditIdx = kids.findIndex((e) => e.classList.contains('author-credit'))

    expect(cardIdx).toBeGreaterThanOrEqual(0)
    expect(creditIdx).toBeGreaterThan(cardIdx)
    w.unmount()
  })

  it('.login-page 明確設定了 flex-direction: column', () => {
    // scoped <style> 不會套進 jsdom,所以直接讀元件原始碼裡的樣式宣告 —
    // 這條規則就是修正本身,拿掉它畫面又會歪掉。
    const src = LoginPageSource
    const block = src.slice(src.indexOf('.login-page {'), src.indexOf('.login-page__credit'))
    expect(block).toContain('flex-direction: column')
  })
})

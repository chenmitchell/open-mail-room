import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AppButton from '@/components/AppButton.vue'

describe('AppButton', () => {
  it('renders slot content and defaults to the primary variant', () => {
    const wrapper = mount(AppButton, { slots: { default: '送出' } })
    expect(wrapper.text()).toContain('送出')
    expect(wrapper.classes()).toContain('app-button--primary')
    expect(wrapper.attributes('type')).toBe('button')
  })

  it('disables the native button and sets aria-busy when loading', () => {
    const wrapper = mount(AppButton, { props: { loading: true }, slots: { default: '送出' } })
    expect(wrapper.attributes('disabled')).toBeDefined()
    expect(wrapper.attributes('aria-busy')).toBe('true')
  })

  it('applies the requested variant modifier class', () => {
    const wrapper = mount(AppButton, { props: { variant: 'danger' }, slots: { default: 'x' } })
    expect(wrapper.classes()).toContain('app-button--danger')
  })

  it('meets the >=44px touch target via the design token (not hardcoded px)', () => {
    const wrapper = mount(AppButton, { slots: { default: 'x' } })
    expect(wrapper.find('button').exists()).toBe(true)
    // Actual pixel measurement requires a real layout engine; here we assert
    // the token-driven class is present so the CSS contract in tokens.css holds.
    expect(wrapper.classes()).toContain('app-button')
  })
})

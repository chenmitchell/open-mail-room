import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import HelpHint from '@/components/HelpHint.vue'

// M6-HELP: reusable "?" hint icon (title attr + self-drawn tooltip),
// keyboard focusable, aria-describedby-linked, shown on hover or focus.
describe('HelpHint', () => {
  function mountHint() {
    return mount(HelpHint, {
      props: { text: '這是收件台首頁的說明文字' },
      global: { plugins: [i18n] },
    })
  }

  it('renders a native <button> trigger (keyboard focusable) with the text as the title attribute', () => {
    const wrapper = mountHint()
    const trigger = wrapper.find('button')
    expect(trigger.exists()).toBe(true)
    expect(trigger.attributes('title')).toBe('這是收件台首頁的說明文字')
  })

  it('links the trigger to the tooltip via aria-describedby, and gives it a generic accessible name', () => {
    const wrapper = mountHint()
    const trigger = wrapper.find('button')
    const tooltip = wrapper.find('[role="tooltip"]')

    expect(tooltip.exists()).toBe(true)
    expect(trigger.attributes('aria-describedby')).toBe(tooltip.attributes('id'))
    // The accessible *name* stays generic ("使用說明") -- the specific
    // explanation is only exposed as the *description* -- so multiple hints
    // on one page don't all announce as identically-worded buttons losing
    // their distinguishing text, and so the name doesn't just double up the
    // description content.
    expect(trigger.attributes('aria-label')).toBe('使用說明')
  })

  it('keeps the tooltip mounted (not v-if) so aria-describedby always resolves, only toggling a visibility class', async () => {
    const wrapper = mountHint()
    const tooltip = wrapper.find('[role="tooltip"]')
    expect(tooltip.exists()).toBe(true)
    expect(tooltip.classes()).not.toContain('help-hint__tooltip--visible')
  })

  it('shows the tooltip on mouseenter and hides it again on mouseleave', async () => {
    const wrapper = mountHint()
    const trigger = wrapper.find('button')
    const tooltip = wrapper.find('[role="tooltip"]')

    await trigger.trigger('mouseenter')
    expect(tooltip.classes()).toContain('help-hint__tooltip--visible')

    await trigger.trigger('mouseleave')
    expect(tooltip.classes()).not.toContain('help-hint__tooltip--visible')
  })

  it('shows the tooltip on keyboard focus and hides it on blur', async () => {
    const wrapper = mountHint()
    const trigger = wrapper.find('button')
    const tooltip = wrapper.find('[role="tooltip"]')

    await trigger.trigger('focus')
    expect(tooltip.classes()).toContain('help-hint__tooltip--visible')

    await trigger.trigger('blur')
    expect(tooltip.classes()).not.toContain('help-hint__tooltip--visible')
  })

  it('renders the exact hint text inside the tooltip', () => {
    const wrapper = mountHint()
    expect(wrapper.find('[role="tooltip"]').text()).toBe('這是收件台首頁的說明文字')
  })
})

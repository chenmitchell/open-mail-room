import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AppBadge from '@/components/AppBadge.vue'

describe('AppBadge', () => {
  it('renders a colour chip, an icon inside it, and the text label together (never colour alone)', () => {
    const wrapper = mount(AppBadge, { props: { status: 'pending', label: '待確認' } })
    expect(wrapper.text()).toContain('待確認')
    expect(wrapper.find('.app-badge__chip').exists()).toBe(true)
    expect(wrapper.find('svg.app-badge__icon').exists()).toBe(true)
    expect(wrapper.find('.app-badge__label').exists()).toBe(true)
  })

  it('marks the decorative chip and icon as aria-hidden so only the text label is announced', () => {
    const wrapper = mount(AppBadge, { props: { status: 'notified', label: '已通知' } })
    expect(wrapper.find('.app-badge__chip').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('svg').attributes('aria-hidden')).toBe('true')
  })

  it('falls back to the status key as the label when no label prop is given', () => {
    const wrapper = mount(AppBadge, { props: { status: 'notified' } })
    expect(wrapper.text()).toContain('notified')
  })

  it('applies a status-specific modifier class carrying the Okabe-Ito colour', () => {
    const wrapper = mount(AppBadge, { props: { status: 'unclaimed', label: '滯留' } })
    expect(wrapper.classes()).toContain('app-badge--unclaimed')
  })

  it.each([
    ['pending', 'app-badge--pending'],
    ['notified', 'app-badge--notified'],
    ['pickedUp', 'app-badge--pickedUp'],
    ['reminder', 'app-badge--reminder'],
    ['unclaimed', 'app-badge--unclaimed'],
    ['outbound', 'app-badge--outbound'],
    ['neutral', 'app-badge--neutral'],
  ] as const)('maps status "%s" to its fixed status modifier class "%s" (chip colour lives in CSS, never inline)', (status, expectedClass) => {
    const wrapper = mount(AppBadge, { props: { status, label: 'x' } })
    expect(wrapper.classes()).toContain(expectedClass)
    // The chip must not carry an inline background — colour comes solely
    // from the CSS modifier class (tokens.css), so templates/snapshots
    // can't drift the status <-> colour mapping independently of the class.
    expect(wrapper.find('.app-badge__chip').attributes('style')).toBeUndefined()
  })

  it('gives reminder and unclaimed visually distinct icon shapes (both are "danger-ish" yellow/vermillion but must not rely on colour alone)', () => {
    const reminder = mount(AppBadge, { props: { status: 'reminder', label: '提醒' } })
    const unclaimed = mount(AppBadge, { props: { status: 'unclaimed', label: '滯留' } })
    const reminderPaths = reminder.findAll('svg path').map((p) => p.attributes('d'))
    const unclaimedPaths = unclaimed.findAll('svg path').map((p) => p.attributes('d'))
    expect(reminderPaths).not.toEqual(unclaimedPaths)
  })
})

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import OtherFieldInput from '@/components/OtherFieldInput.vue'

// UX-VISUAL task B: shared "選其他 -> 即時展開必填輸入框" widget shared by
// carrier/mail_type/payment dropdowns on InboundRegisterPage/OutboundPage.
describe('OtherFieldInput', () => {
  it('renders nothing when show is false', () => {
    const wrapper = mount(OtherFieldInput, {
      props: { show: false, modelValue: '', label: '其他承運商名稱' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('renders a required text input with the given label when show is true', () => {
    const wrapper = mount(OtherFieldInput, {
      props: { show: true, modelValue: '', label: '其他承運商名稱' },
      global: { plugins: [i18n] },
    })
    const input = wrapper.find('input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('required')).toBeDefined()
    expect(wrapper.text()).toContain('其他承運商名稱')
  })

  it('emits update:modelValue as the user types', async () => {
    const wrapper = mount(OtherFieldInput, {
      props: { show: true, modelValue: '', label: '其他承運商名稱' },
      global: { plugins: [i18n] },
    })
    await wrapper.find('input').setValue('順風貨運')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['順風貨運'])
  })

  it('surfaces a validation error message when the error prop is set', () => {
    const wrapper = mount(OtherFieldInput, {
      props: {
        show: true,
        modelValue: '',
        label: '其他承運商名稱',
        error: '已選擇「其他」,請輸入其他承運商名稱。',
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('已選擇「其他」,請輸入其他承運商名稱。')
  })
})

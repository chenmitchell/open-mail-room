import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { i18n } from '@/i18n'
import EmployeeMatchChips from '@/components/EmployeeMatchChips.vue'

describe('EmployeeMatchChips', () => {
  const candidates = [
    { employee_id: 'e1', name: '王小明', department_name: '行銷部', score: 95 },
    { employee_id: 'e2', name: '王小名', department_name: '業務部', score: 78 },
  ]

  it('renders one chip per candidate with name, department, and score', () => {
    const wrapper = mount(EmployeeMatchChips, {
      props: { candidates, modelValue: null },
      global: { plugins: [i18n] },
    })

    const chips = wrapper.findAll('.employee-match-chips__chip')
    expect(chips).toHaveLength(2)
    expect(chips[0].text()).toContain('王小明')
    expect(chips[0].text()).toContain('行銷部')
    expect(chips[0].text()).toContain('95%')
    expect(chips[1].text()).toContain('78%')
  })

  it('renders nothing when there are no candidates', () => {
    const wrapper = mount(EmployeeMatchChips, {
      props: { candidates: [], modelValue: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.employee-match-chips').exists()).toBe(false)
  })

  it('emits the employee id on click and marks it aria-pressed / selected', async () => {
    const wrapper = mount(EmployeeMatchChips, {
      props: { candidates, modelValue: null },
      global: { plugins: [i18n] },
    })

    const firstChip = wrapper.findAll('.employee-match-chips__chip')[0]
    await firstChip.trigger('click')
    expect(wrapper.emitted('update:modelValue')![0]).toEqual(['e1'])

    await wrapper.setProps({ modelValue: 'e1' })
    expect(firstChip.attributes('aria-pressed')).toBe('true')
    expect(firstChip.classes()).toContain('employee-match-chips__chip--selected')
  })

  it('clicking an already-selected chip deselects it (toggle)', async () => {
    const wrapper = mount(EmployeeMatchChips, {
      props: { candidates, modelValue: 'e1' },
      global: { plugins: [i18n] },
    })
    await wrapper.findAll('.employee-match-chips__chip')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')![0]).toEqual([null])
  })
})

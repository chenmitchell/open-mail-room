import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

vi.mock('@/api/carriers', () => ({ listCarriers: vi.fn() }))
vi.mock('@/api/employees', () => ({ matchEmployees: vi.fn() }))
vi.mock('@/api/items', () => ({ createItem: vi.fn() }))

import { listCarriers } from '@/api/carriers'
import { matchEmployees } from '@/api/employees'
import { createItem } from '@/api/items'
import InboundRegisterPage from '@/pages/inbound/InboundRegisterPage.vue'
import type { MailItem } from '@/types/api'

function mailItem(overrides: Partial<MailItem> = {}): MailItem {
  return {
    id: 'm1',
    item_no: 'IN-20260713-0001',
    mail_type: 'parcel',
    recipient_name_raw: '王小明',
    status: 'pending',
    ...overrides,
  } as MailItem
}

function mountPage() {
  return mount(InboundRegisterPage, { global: { plugins: [i18n] } })
}

function findFieldByLabel(wrapper: ReturnType<typeof mount>, labelText: string) {
  // Match on the label's own text *starting with* labelText rather than a
  // substring anywhere in the field -- "備註" is itself a substring of
  // "尺寸/重量備註" (sizeNoteLabel), so a plain `.includes` would grab the
  // wrong field.
  return wrapper
    .findAll('.app-input')
    .find((w) => w.find('.app-input__label').text().startsWith(labelText))
}

// UX-VISUAL task B: 承運商下拉選到「其他」-> 即時展開必填輸入框,送出時併入 note.
describe('InboundRegisterPage — "其他" carrier free-text field', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  function stubLookupsWithOtherCarrier() {
    vi.mocked(listCarriers).mockResolvedValue({
      items: [
        { id: 'c1', name: '中華郵政掛號/包裹', slug: 'chunghwa_post', kind: 'postal', is_active: true },
        { id: 'c2', name: '其他', slug: 'other', kind: 'other', is_active: true },
      ],
      meta: { total: 2, page: 1, size: 20 },
    })
    vi.mocked(matchEmployees).mockResolvedValue([])
  }

  it('does not show the free-text field until "其他" is selected', async () => {
    stubLookupsWithOtherCarrier()
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).not.toContain('其他承運商名稱')
  })

  it('reveals a required free-text field when the carrier select resolves to "其他", and hides it again when switched away', async () => {
    stubLookupsWithOtherCarrier()
    const wrapper = mountPage()
    await flushPromises()

    const carrierSelect = wrapper.findAll('select')[1]
    await carrierSelect.setValue('c2')
    await flushPromises()

    expect(wrapper.text()).toContain('其他承運商名稱')
    const otherField = findFieldByLabel(wrapper, '其他承運商名稱')
    expect(otherField?.find('input').attributes('required')).toBeDefined()

    await carrierSelect.setValue('c1')
    await flushPromises()
    expect(wrapper.text()).not.toContain('其他承運商名稱')
  })

  it('blocks submit with a validation error when "其他" is selected but the free-text field is left blank', async () => {
    stubLookupsWithOtherCarrier()
    const wrapper = mountPage()
    await flushPromises()

    const mailTypeSelect = wrapper.findAll('select')[0]
    await mailTypeSelect.setValue('parcel')

    const recipientField = findFieldByLabel(wrapper, '收件人姓名')
    await recipientField!.find('input').setValue('王小明')

    const carrierSelect = wrapper.findAll('select')[1]
    await carrierSelect.setValue('c2')
    await flushPromises()

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('已選擇「其他」,請輸入其他承運商名稱。')
    expect(createItem).not.toHaveBeenCalled()
  })

  it('merges the free-text value into note (prefixed) on submit, preserving the user’s own note', async () => {
    stubLookupsWithOtherCarrier()
    vi.mocked(createItem).mockResolvedValue(mailItem())
    const wrapper = mountPage()
    await flushPromises()

    const mailTypeSelect = wrapper.findAll('select')[0]
    await mailTypeSelect.setValue('parcel')

    const recipientField = findFieldByLabel(wrapper, '收件人姓名')
    await recipientField!.find('input').setValue('王小明')

    const carrierSelect = wrapper.findAll('select')[1]
    await carrierSelect.setValue('c2')
    await flushPromises()

    const otherField = findFieldByLabel(wrapper, '其他承運商名稱')
    expect(otherField).toBeTruthy()
    await otherField!.find('input').setValue('順風貨運')

    const noteField = findFieldByLabel(wrapper, '備註')
    await noteField!.find('input').setValue('易碎品')

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createItem).toHaveBeenCalledWith(
      expect.objectContaining({ note: '承運商(其他):順風貨運\n易碎品' }),
    )
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'

// 01 §2.2 交寄(outbound) / 06 §1 「交寄」頁: 建立交寄單(申請人自動帶入、部
// 門、收件人資訊、承運商下拉、付款方式)、交寄清單(篩選狀態)、「已交寄」動作.
vi.mock('@/api/outbound', () => ({
  listOutbound: vi.fn(),
  createOutbound: vi.fn(),
  markOutboundShipped: vi.fn(),
}))
vi.mock('@/api/carriers', () => ({ listCarriers: vi.fn() }))
vi.mock('@/api/departments', () => ({ listDepartments: vi.fn() }))
vi.mock('@/api/employees', () => ({ matchEmployees: vi.fn() }))
vi.mock('@/api/uploads', () => ({ uploadPhotos: vi.fn() }))
vi.mock('@/api/ocr', () => ({ createOcrJob: vi.fn(), getOcrJob: vi.fn(), getOcrDraft: vi.fn() }))

import { createOutbound, listOutbound, markOutboundShipped } from '@/api/outbound'
import { listCarriers } from '@/api/carriers'
import { listDepartments } from '@/api/departments'
import { matchEmployees } from '@/api/employees'
import OutboundPage from '@/pages/outbound/OutboundPage.vue'
import type { OutboundItem } from '@/types/api'

function outboundItem(overrides: Partial<OutboundItem> = {}): OutboundItem {
  return {
    id: 'o1',
    item_no: 'OUT-20260712-0001',
    to_name: '客戶 A',
    status: 'pending',
    ...overrides,
  }
}

function stubEmptyLookups() {
  vi.mocked(listCarriers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  vi.mocked(listDepartments).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  vi.mocked(matchEmployees).mockResolvedValue([])
}

function mountPage(attachToBody = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role: 'counter' }
  const wrapper = mount(OutboundPage, {
    global: { plugins: [i18n, pinia] },
    ...(attachToBody ? { attachTo: document.body } : {}),
  })
  return { wrapper, auth }
}

describe('OutboundPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('pre-fills the applicant field with the logged-in user’s display name', async () => {
    vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    stubEmptyLookups()

    const { wrapper } = mountPage()
    await flushPromises()

    const applicantInput = wrapper.find('input[type="text"]')
    expect((applicantInput.element as HTMLInputElement).value).toBe('王小明')
  })

  it('requires a recipient name (toName) before submitting the create form', async () => {
    vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    stubEmptyLookups()

    const { wrapper } = mountPage()
    await flushPromises()

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入收件人姓名')
    expect(createOutbound).not.toHaveBeenCalled()
  })

  it('creates an outbound item with the recipient name and shows the success message', async () => {
    vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    stubEmptyLookups()
    vi.mocked(createOutbound).mockResolvedValue(outboundItem({ item_no: 'OUT-20260712-0007' }))

    const { wrapper } = mountPage()
    await flushPromises()

    const toNameInputs = wrapper.findAll('input[type="text"]')
    // [0] = applicant, [1] = toName (first two AppInput text fields on the create form)
    await toNameInputs[1].setValue('客戶 A')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createOutbound).toHaveBeenCalledWith(expect.objectContaining({ to_name: '客戶 A' }))
    expect(wrapper.text()).toContain('OUT-20260712-0007')
  })

  it('re-fetches the list with the selected status when the filter is applied', async () => {
    vi.mocked(listOutbound).mockResolvedValue({
      items: [outboundItem()],
      meta: { total: 1, page: 1, size: 20 },
    })
    stubEmptyLookups()

    const { wrapper } = mountPage()
    await flushPromises()

    const filterForm = wrapper.findAll('form')[1]
    const statusSelect = filterForm.find('select')
    await statusSelect.setValue('shipped')
    await filterForm.trigger('submit.prevent')
    await flushPromises()

    expect(listOutbound).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'shipped' }))
  })

  it('marks a pending item as shipped with a manually entered tracking number', async () => {
    vi.mocked(listOutbound).mockResolvedValue({
      items: [outboundItem({ id: 'o9', status: 'pending' })],
      meta: { total: 1, page: 1, size: 20 },
    })
    stubEmptyLookups()
    vi.mocked(markOutboundShipped).mockResolvedValue(outboundItem({ id: 'o9', status: 'shipped' }))

    const { wrapper } = mountPage(true)
    await flushPromises()

    const shipButton = wrapper.findAll('button').find((b) => b.text() === '標記已交寄')
    await shipButton?.trigger('click')
    await flushPromises()

    // AppDialog renders via <Teleport to="body"> — query through the body
    // once open, same convention as tests/pages/NotificationSettingsPage.spec.ts.
    const body = new DOMWrapper(document.body)
    const trackingInput = body.find('.app-dialog input[type="text"]')
    await trackingInput.setValue('1234567890')

    const confirmButton = body.findAll('.app-dialog__footer button').find((b) => b.text() === '確認已交寄')
    expect(confirmButton).toBeTruthy()
    await confirmButton?.trigger('click')
    await flushPromises()

    expect(markOutboundShipped).toHaveBeenCalledWith('o9', {
      tracking_no: '1234567890',
      attachment_id: undefined,
    })

    wrapper.unmount()
  })

  // UX-VISUAL task B: 承運商下拉選到「其他」-> 即時展開必填輸入框,送出時併入 note.
  describe('"其他" carrier -> free-text field', () => {
    function stubLookupsWithOtherCarrier() {
      vi.mocked(listCarriers).mockResolvedValue({
        items: [
          { id: 'c1', name: '黑貓宅急便', slug: 'tcat', kind: 'courier', is_active: true },
          { id: 'c2', name: '其他', slug: 'other', kind: 'other', is_active: true },
        ],
        meta: { total: 2, page: 1, size: 20 },
      })
      vi.mocked(listDepartments).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
      vi.mocked(matchEmployees).mockResolvedValue([])
    }

    function findFieldByLabel(wrapper: ReturnType<typeof mount>, labelText: string) {
      return wrapper.findAll('.app-input').find((w) => w.text().includes(labelText))
    }

    it('does not show the free-text field until "其他" is selected', async () => {
      vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
      stubLookupsWithOtherCarrier()

      const { wrapper } = mountPage()
      await flushPromises()

      expect(wrapper.text()).not.toContain('其他承運商名稱')
    })

    it('reveals a required free-text field when the carrier select resolves to "其他", and hides it again when switched away', async () => {
      vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
      stubLookupsWithOtherCarrier()

      const { wrapper } = mountPage()
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
      vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
      stubLookupsWithOtherCarrier()

      const { wrapper } = mountPage()
      await flushPromises()

      const toNameInputs = wrapper.findAll('input[type="text"]')
      await toNameInputs[1].setValue('客戶 A')

      const carrierSelect = wrapper.findAll('select')[1]
      await carrierSelect.setValue('c2')
      await flushPromises()

      await wrapper.find('form').trigger('submit.prevent')
      await flushPromises()

      expect(wrapper.text()).toContain('已選擇「其他」,請輸入其他承運商名稱。')
      expect(createOutbound).not.toHaveBeenCalled()
    })

    it('merges the free-text value into note (prefixed) on submit, preserving the user’s own note', async () => {
      vi.mocked(listOutbound).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
      stubLookupsWithOtherCarrier()
      vi.mocked(createOutbound).mockResolvedValue(outboundItem({ item_no: 'OUT-20260713-0001' }))

      const { wrapper } = mountPage()
      await flushPromises()

      const toNameInputs = wrapper.findAll('input[type="text"]')
      await toNameInputs[1].setValue('客戶 A')

      const carrierSelect = wrapper.findAll('select')[1]
      await carrierSelect.setValue('c2')
      await flushPromises()

      const otherField = findFieldByLabel(wrapper, '其他承運商名稱')
      expect(otherField).toBeTruthy()
      await otherField!.find('input').setValue('順風貨運')

      const noteField = findFieldByLabel(wrapper, '備註')
      expect(noteField).toBeTruthy()
      await noteField!.find('input').setValue('易碎品')

      await wrapper.find('form').trigger('submit.prevent')
      await flushPromises()

      expect(createOutbound).toHaveBeenCalledWith(
        expect.objectContaining({ note: '承運商(其他):順風貨運\n易碎品' }),
      )
    })
  })
})
